"""Quaternion kernels, written once and compiled for the CPU or the GPU.

Every operation below is defined as a plain scalar Python body. numba compiles
each body twice — as an ``njit`` device function for the parallel CPU target and
as a ``cuda.jit`` device function for the CUDA target — and ``guvectorize`` wraps
it into a broadcasting ufunc. So the maths exists in exactly one place and the
two targets cannot drift; the tests assert they agree with the numpy reference.

Why our own kernels rather than a tensor library: these are elementwise
quaternion products plus a min over the ~24 symmetry operators. None of it is
GEMM/convolution/FFT, so a tuned BLAS buys nothing — whereas a tensor library
launches a separate kernel per arithmetic step and materialises every
intermediate (in :meth:`pairwise_below` that is an ``(N, N, 24)`` array). Fusing
each operation into one kernel keeps the intermediates in registers, and needs
only the CUDA *compiler* (~60 MB) instead of ~3.7 GB of neural-network libraries.

The GPU path uses float32 (consumer cards run float64 at ~1/32 rate); the
resulting angle error is ~1e-3°, far below the degrees-scale thresholds the
reconstruction compares against.
"""

import logging
import math
import os
import sys
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

_SQRT2 = float(np.sqrt(2.0))


# --------------------------------------------------------------------------
# Scalar bodies. Plain Python — compiled per target, never executed directly.
# --------------------------------------------------------------------------


def _qmul_body(a, b, out):
    """out = a * b (Hamilton product)."""
    out[0] = a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3]
    out[1] = a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2]
    out[2] = a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1]
    out[3] = a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]


def _disor_body(q1, q2, sym):
    """Symmetry-reduced disorientation angle between q1 and q2, in degrees."""
    # mori = q1 * conj(q2)
    mw = q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]
    mx = -q1[0] * q2[1] + q1[1] * q2[0] - q1[2] * q2[3] + q1[3] * q2[2]
    my = -q1[0] * q2[2] + q1[1] * q2[3] + q1[2] * q2[0] - q1[3] * q2[1]
    mz = -q1[0] * q2[3] - q1[1] * q2[2] + q1[2] * q2[1] + q1[3] * q2[0]
    # smallest angle over the symmetry group == largest |w| of sym * mori
    best = 0.0
    for s in range(sym.shape[0]):
        w = abs(sym[s, 0] * mw - sym[s, 1] * mx - sym[s, 2] * my - sym[s, 3] * mz)
        if w > best:
            best = w
    if best > 1.0:
        best = 1.0
    return math.degrees(2.0 * math.acos(best))


def _cand_body(variants, child, out):
    """out[v] = conj(variants[v]) * child, hemisphere-aligned (w >= 0)."""
    for v in range(variants.shape[0]):
        vw, vx, vy, vz = variants[v, 0], variants[v, 1], variants[v, 2], variants[v, 3]
        cw, cx, cy, cz = child[0], child[1], child[2], child[3]
        w = vw * cw + vx * cx + vy * cy + vz * cz
        x = vw * cx - vx * cw - vy * cz + vz * cy
        y = vw * cy + vx * cz - vy * cw - vz * cx
        z = vw * cz - vx * cy + vy * cx - vz * cw
        sign = -1.0 if w < 0.0 else 1.0
        out[v, 0] = w * sign
        out[v, 1] = x * sign
        out[v, 2] = y * sign
        out[v, 3] = z * sign


def _best_variant_body(variants, parent, child, out):
    """Index of the variant whose predicted child best matches the observed one."""
    best_w = -1.0
    best_i = 0
    for v in range(variants.shape[0]):
        # predicted = variants[v] * parent
        pw = variants[v, 0] * parent[0] - variants[v, 1] * parent[1] \
            - variants[v, 2] * parent[2] - variants[v, 3] * parent[3]
        px = variants[v, 0] * parent[1] + variants[v, 1] * parent[0] \
            + variants[v, 2] * parent[3] - variants[v, 3] * parent[2]
        py = variants[v, 0] * parent[2] - variants[v, 1] * parent[3] \
            + variants[v, 2] * parent[0] + variants[v, 3] * parent[1]
        pz = variants[v, 0] * parent[3] + variants[v, 1] * parent[2] \
            - variants[v, 2] * parent[1] + variants[v, 3] * parent[0]
        # |(conj(predicted) * child).w|
        w = abs(pw * child[0] + px * child[1] + py * child[2] + pz * child[3])
        if w > best_w:
            best_w = w
            best_i = v
    out[0] = best_i


def _fit_body(variants, parent, child, sym, out):
    """Smallest disorientation between any candidate parent and the given parent."""
    best = 1e30
    for v in range(variants.shape[0]):
        vw, vx, vy, vz = variants[v, 0], variants[v, 1], variants[v, 2], variants[v, 3]
        cw, cx, cy, cz = child[0], child[1], child[2], child[3]
        # cand = conj(variants[v]) * child
        q0 = vw * cw + vx * cx + vy * cy + vz * cz
        q1 = vw * cx - vx * cw - vy * cz + vz * cy
        q2 = vw * cy + vx * cz - vy * cw - vz * cx
        q3 = vw * cz - vx * cy + vy * cx - vz * cw
        # mori = cand * conj(parent)
        mw = q0 * parent[0] + q1 * parent[1] + q2 * parent[2] + q3 * parent[3]
        mx = -q0 * parent[1] + q1 * parent[0] - q2 * parent[3] + q3 * parent[2]
        my = -q0 * parent[2] + q1 * parent[3] + q2 * parent[0] - q3 * parent[1]
        mz = -q0 * parent[3] - q1 * parent[2] + q2 * parent[1] + q3 * parent[0]
        top = 0.0
        for s in range(sym.shape[0]):
            w = abs(sym[s, 0] * mw - sym[s, 1] * mx - sym[s, 2] * my - sym[s, 3] * mz)
            if w > top:
                top = w
        if top > 1.0:
            top = 1.0
        ang = math.degrees(2.0 * math.acos(top))
        if ang < best:
            best = ang
    out[0] = best


def _edge_body(cand_i, cand_j, sym, out):
    """out[a, b] = disorientation between candidate a of i and candidate b of j."""
    for a in range(cand_i.shape[0]):
        for b in range(cand_j.shape[0]):
            mw = cand_i[a, 0] * cand_j[b, 0] + cand_i[a, 1] * cand_j[b, 1] \
                + cand_i[a, 2] * cand_j[b, 2] + cand_i[a, 3] * cand_j[b, 3]
            mx = -cand_i[a, 0] * cand_j[b, 1] + cand_i[a, 1] * cand_j[b, 0] \
                - cand_i[a, 2] * cand_j[b, 3] + cand_i[a, 3] * cand_j[b, 2]
            my = -cand_i[a, 0] * cand_j[b, 2] + cand_i[a, 1] * cand_j[b, 3] \
                + cand_i[a, 2] * cand_j[b, 0] - cand_i[a, 3] * cand_j[b, 1]
            mz = -cand_i[a, 0] * cand_j[b, 3] - cand_i[a, 1] * cand_j[b, 2] \
                + cand_i[a, 2] * cand_j[b, 1] + cand_i[a, 3] * cand_j[b, 0]
            top = 0.0
            for s in range(sym.shape[0]):
                w = abs(sym[s, 0] * mw - sym[s, 1] * mx - sym[s, 2] * my - sym[s, 3] * mz)
                if w > top:
                    top = w
            if top > 1.0:
                top = 1.0
            out[a, b] = math.degrees(2.0 * math.acos(top))



def _refine_cost_body(qi, qj, variants, sym, out):
    """Best symmetry-reduced angle between any pair of candidate parents.

    For one neighbouring grain pair: over every (a, b) variant combination, the
    disorientation between qi's candidate parent a and qj's candidate parent b;
    the output is the smallest. Everything is scalar — the reference version
    allocated two numpy arrays per innermost iteration, which dominated its cost.
    """
    best = 1e30
    n_var = variants.shape[0]
    for a in range(n_var):
        # pi = qi * conj(variants[a])
        aw, ax, ay, az = variants[a, 0], -variants[a, 1], -variants[a, 2], -variants[a, 3]
        pw = qi[0] * aw - qi[1] * ax - qi[2] * ay - qi[3] * az
        px = qi[0] * ax + qi[1] * aw + qi[2] * az - qi[3] * ay
        py = qi[0] * ay - qi[1] * az + qi[2] * aw + qi[3] * ax
        pz = qi[0] * az + qi[1] * ay - qi[2] * ax + qi[3] * aw
        for b in range(n_var):
            bw, bx, by, bz = variants[b, 0], -variants[b, 1], -variants[b, 2], -variants[b, 3]
            rw = qj[0] * bw - qj[1] * bx - qj[2] * by - qj[3] * bz
            rx = qj[0] * bx + qj[1] * bw + qj[2] * bz - qj[3] * by
            ry = qj[0] * by - qj[1] * bz + qj[2] * bw + qj[3] * bx
            rz = qj[0] * bz + qj[1] * by - qj[2] * bx + qj[3] * bw
            # disorientation between the two candidate parents
            mw = pw * rw + px * rx + py * ry + pz * rz
            mx = -pw * rx + px * rw - py * rz + pz * ry
            my = -pw * ry + px * rz + py * rw - pz * rx
            mz = -pw * rz - px * ry + py * rx + pz * rw
            top = 0.0
            for si in range(sym.shape[0]):
                w = abs(sym[si, 0] * mw - sym[si, 1] * mx - sym[si, 2] * my - sym[si, 3] * mz)
                if w > top:
                    top = w
            if top > 1.0:
                top = 1.0
            ang = math.degrees(2.0 * math.acos(top))
            if ang < best:
                best = ang
    out[0] = best


# --------------------------------------------------------------------------
# Compilation. Each body becomes a gufunc for the requested target.
# --------------------------------------------------------------------------


def _use_bundled_cuda() -> None:
    """Point numba at the CUDA compiler shipped inside the frozen bundle.

    A user with a graphics card has the display driver but usually no CUDA
    toolkit, so NVVM (needed to COMPILE kernels) would be missing. The bundle
    carries it; an explicit CUDA_HOME from the environment still wins.
    """
    if os.environ.get("CUDA_HOME") or os.environ.get("CUDA_PATH"):
        return
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return
    bundled = os.path.join(base, "cuda")
    if os.path.isdir(bundled):
        os.environ["CUDA_HOME"] = bundled


def cuda_available() -> bool:
    """True when numba can compile and launch CUDA kernels on this machine."""
    try:
        _use_bundled_cuda()
        from numba import cuda

        return bool(cuda.is_available())
    except Exception:  # noqa: BLE001 — a broken CUDA install must not crash the app
        return False


class _Kernels:
    """Compiled gufuncs for one target, plus the array plumbing around them."""

    def __init__(self, use_cuda: bool):
        from numba import cuda, float32, float64, guvectorize, int32, njit

        self.use_cuda = use_cuda
        self.device = "cuda" if use_cuda else "cpu"
        # These kernels are launch/bandwidth-bound rather than FLOP-bound, so
        # float64 on the GPU costs little and keeps results bit-comparable with
        # the numpy reference. PAGB_FP32=1 trades that for speed.
        _fp32 = use_cuda and os.environ.get("PAGB_FP32", "").strip() == "1"
        self.dtype = np.float32 if _fp32 else np.float64
        f = float32 if _fp32 else float64
        target = "cuda" if use_cuda else "parallel"
        wrap = (lambda fn: cuda.jit(device=True)(fn)) if use_cuda else (
            lambda fn: njit(inline="always")(fn)
        )
        disor = wrap(_disor_body)

        def gu(sigs, layout, body):
            return guvectorize(sigs, layout, target=target)(body)

        self._multiply = gu([(f[:], f[:], f[:])], "(n),(n)->(n)", _qmul_body)

        def _disor_kernel(q1, q2, sym, out):
            out[0] = disor(q1, q2, sym)

        self._disor = gu([(f[:], f[:], f[:, :], f[:])], "(n),(n),(s,n)->()", _disor_kernel)
        self._cand = gu([(f[:, :], f[:], f[:, :])], "(v,n),(n)->(v,n)", _cand_body)
        self._best = gu(
            [(f[:, :], f[:], f[:], int32[:])], "(v,n),(n),(n)->()", _best_variant_body
        )
        self._fit = gu(
            [(f[:, :], f[:], f[:], f[:, :], f[:])],
            "(v,n),(n),(n),(s,n)->()",
            _fit_body,
        )
        self._edges = gu(
            [(f[:, :], f[:, :], f[:, :], f[:, :])],
            "(v,n),(w,n),(s,n)->(v,w)",
            _edge_body,
        )
        self._refine = gu(
            [(f[:], f[:], f[:, :], f[:, :], f[:])],
            "(n),(n),(v,n),(s,n)->()",
            _refine_cost_body,
        )

    def self_test(self) -> None:
        """Force compilation and a launch, so an unusable CUDA install fails here
        (where we can fall back) rather than mid-reconstruction."""
        q = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        sym = np.array([[1.0, 0.0, 0.0, 0.0]])
        self.multiply(q, q)
        self.disorientation_deg(q, q, sym)
        self.best_variant(q, q, q)
        self.fit_angles(q, q, q, sym)
        self.candidate_parents(q, q)
        self.refine_or_cost(q, q, q, sym)

    def _a(self, x) -> np.ndarray:
        return np.ascontiguousarray(x, dtype=self.dtype)

    def _pair(self, a, b):
        """Broadcast two quaternion arrays to a common shape, materialised.

        A CUDA gufunc cannot expand a size-1 loop axis the way numpy does, so the
        broadcast has to be real. Doing it for both targets keeps the backends
        behaving identically.
        """
        a, b = self._a(a), self._a(b)
        shape = np.broadcast_shapes(a.shape[:-1], b.shape[:-1])
        return (
            np.ascontiguousarray(np.broadcast_to(a, (*shape, 4))),
            np.ascontiguousarray(np.broadcast_to(b, (*shape, 4))),
        )

    # -- public API, mirroring the numpy backend -----------------------------

    def multiply(self, a, b):
        a, b = self._pair(a, b)
        return self._multiply(a, b).astype(np.float64)

    def disorientation_deg(self, q1, q2, sym_quats):
        q1, q2 = self._pair(q1, q2)
        return self._disor(q1, q2, self._a(sym_quats)).astype(np.float64)

    def candidate_parents(self, variants, child):
        # variants carries only core dims (v,n), so it broadcasts across the
        # child loop dimension on both targets — no size-1 loop axis, which the
        # CUDA gufunc does not support.
        v, c = self._a(variants), self._a(child)
        return self._cand(v, c).astype(np.float64)

    def best_variant(self, variants, parent, child):
        v, p, c = self._a(variants), self._a(parent), self._a(child)
        return self._best(v, p, c).astype(np.int32)

    def fit_angles(self, variants, parent, child, sym_quats):
        v, p, c = self._a(variants), self._a(parent), self._a(child)
        return self._fit(v, p, c, self._a(sym_quats)).astype(np.float64)

    def refine_or_cost(self, pair_qi, pair_qj, variants, sym_quats) -> float:
        """Mean best-angle over neighbouring grain pairs — the OR refinement cost."""
        per_pair = self._refine(
            self._a(pair_qi), self._a(pair_qj), self._a(variants), self._a(sym_quats)
        )
        return float(np.asarray(per_pair, dtype=np.float64).mean())

    def _row_step(self, inner: int) -> int:
        """Rows per chunk so an intermediate stays around 200 MB."""
        return max(1, 200_000_000 // (max(inner, 1) * self.dtype().itemsize))

    def pairwise_below(self, quats, sym_quats, threshold_deg: float):
        q, sym = self._a(quats), self._a(sym_quats)
        n = q.shape[0]
        out = np.zeros((n, n), dtype=bool)
        step = self._row_step(n * sym.shape[0])
        for r in range(0, n, step):
            lhs, rhs = self._pair(q[r : r + step, None, :], q[None, :, :])
            ang = self._disor(lhs, rhs, sym)
            out[r : r + step] = np.triu(ang < threshold_deg, k=r + 1)
        return out

    def variant_edges(
        self, all_candidates, edge_pairs, sym_quats, threshold_deg, tolerance_deg, min_weight
    ):
        from scipy.special import erf

        cand, sym = self._a(all_candidates), self._a(sym_quats)
        n_var = cand.shape[1]
        ei, ej = edge_pairs[:, 0], edge_pairs[:, 1]
        rows, cols, weights = [], [], []
        step = self._row_step(n_var * n_var * sym.shape[0])
        for e in range(0, len(edge_pairs), step):
            si, sj = ei[e : e + step], ej[e : e + step]
            ang = self._edges(cand[si], cand[sj], sym).astype(np.float64)
            if tolerance_deg > 0:
                weight = 0.5 * (1.0 + erf((threshold_deg - ang) / (tolerance_deg * _SQRT2)))
            else:
                weight = (ang <= threshold_deg).astype(np.float64)
            ke, va, vb = np.where(weight > min_weight)
            rows.append(si[ke] * n_var + va)
            cols.append(sj[ke] * n_var + vb)
            weights.append(weight[ke, va, vb])
        if not rows:
            empty_i = np.empty(0, dtype=np.int64)
            return empty_i, empty_i.copy(), np.empty(0, dtype=np.float64)
        return np.concatenate(rows), np.concatenate(cols), np.concatenate(weights)


@lru_cache(maxsize=2)
def kernels(use_cuda: bool | None = None) -> _Kernels:
    """Compiled kernels for this machine (CUDA when usable, else parallel CPU).

    Compilation is deferred to first use — it costs a few seconds and must not be
    paid at application start.

    A present GPU driver is not enough: compiling CUDA kernels also needs NVVM,
    which a user with only a display driver will not have. So we compile and
    launch once here, and fall back to the CPU target if anything fails —
    otherwise the app would die mid-reconstruction on such a machine.
    """
    if use_cuda is None:
        use_cuda = cuda_available()
    if use_cuda:
        try:
            compiled = _Kernels(True)
            compiled.self_test()
            return compiled
        except Exception as e:  # noqa: BLE001 — any CUDA problem means "use the CPU"
            logger.warning("GPU kernels unavailable (%s: %s); using CPU", type(e).__name__, e)
    return _Kernels(False)
