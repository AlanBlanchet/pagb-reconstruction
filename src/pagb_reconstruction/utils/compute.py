"""Device-aware batched quaternion algebra — GPU when available, numpy otherwise.

The reconstruction hot loops are batched quaternion operations: variant/parent
products, symmetry-reduced disorientations, pairwise parent comparisons, the
variant-edge graph. :data:`Quaternions` binds to the accelerated backend, whose
kernels are compiled from one scalar source (:mod:`.quaternion_kernels`) for
CUDA when the machine has an NVIDIA GPU and for the parallel CPU target
otherwise. :class:`_NumpyQuaternions` stays as the reference implementation the
kernels are tested against, and as the fallback if numba cannot compile.

Set ``PAGB_DEVICE=cpu`` to force the numpy reference (useful when debugging a
suspected kernel problem).
"""

import os

import numpy as np

from pagb_reconstruction.utils import quaternion_kernels

try:  # compiled Rust kernels; optional, selected automatically when present
    import pagb_kernels as _rust

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False

_SQRT2 = float(np.sqrt(2.0))


class _NumpyQuaternions:
    """CPU quaternion algebra in numpy — the reference the kernels are tested against."""

    device = "cpu"

    @staticmethod
    def _mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
        bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
        return np.stack(
            [
                aw * bw - ax * bx - ay * by - az * bz,
                aw * bx + ax * bw + ay * bz - az * by,
                aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw,
            ],
            axis=-1,
        )

    @staticmethod
    def _conj(q: np.ndarray) -> np.ndarray:
        out = q.copy()
        out[..., 1:] *= -1
        return out

    @classmethod
    def _disor(cls, q1: np.ndarray, q2: np.ndarray, sym: np.ndarray) -> np.ndarray:
        mori = cls._mul(q1, cls._conj(q2))
        equiv_w = cls._mul(sym, mori[..., None, :])[..., 0]
        w = np.clip(np.abs(equiv_w), 0.0, 1.0)
        return np.degrees(2.0 * np.arccos(w)).min(axis=-1)

    @classmethod
    def multiply(cls, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return cls._mul(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))

    @classmethod
    def disorientation_deg(cls, q1, q2, sym_quats) -> np.ndarray:
        return cls._disor(
            np.asarray(q1, np.float64), np.asarray(q2, np.float64), np.asarray(sym_quats, np.float64)
        )

    @classmethod
    def candidate_parents(cls, variants: np.ndarray, child: np.ndarray) -> np.ndarray:
        v = np.asarray(variants, np.float64)
        c = np.asarray(child, np.float64)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])
        return cand * np.where(cand[..., :1] < 0, -1.0, 1.0)

    @classmethod
    def best_variant(cls, variants, parent, child) -> np.ndarray:
        v = np.asarray(variants, np.float64)
        p = np.asarray(parent, np.float64)
        c = np.asarray(child, np.float64)
        predicted = cls._mul(v[None, :, :], p[:, None, :])
        mori = cls._mul(cls._conj(predicted), c[:, None, :])
        return np.argmax(np.abs(mori[..., 0]), axis=1).astype(np.int32)

    @classmethod
    def fit_angles(cls, variants, parent, child, sym_quats) -> np.ndarray:
        v = np.asarray(variants, np.float64)
        p = np.asarray(parent, np.float64)
        c = np.asarray(child, np.float64)
        sym = np.asarray(sym_quats, np.float64)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])
        return cls._disor(cand, p[:, None, :], sym).min(axis=1)

    @classmethod
    def pairwise_below(cls, quats, sym_quats, threshold_deg: float) -> np.ndarray:
        q = np.asarray(quats, np.float64)
        sym = np.asarray(sym_quats, np.float64)
        n = q.shape[0]
        out = np.zeros((n, n), dtype=bool)
        # chunk over rows to bound the (rows, n, S) intermediate
        step = max(1, 40_000_000 // max(n * sym.shape[0], 1))
        for r in range(0, n, step):
            dmat = cls._disor(q[r : r + step, None, :], q[None, :, :], sym)
            out[r : r + step] = np.triu(dmat < threshold_deg, k=r + 1)
        return out

    @classmethod
    def variant_edges(
        cls, all_candidates, edge_pairs, sym_quats, threshold_deg, tolerance_deg, min_weight
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        from scipy.special import erf

        cand = np.asarray(all_candidates, np.float64)
        sym = np.asarray(sym_quats, np.float64)
        n_var = cand.shape[1]
        ei, ej = edge_pairs[:, 0], edge_pairs[:, 1]
        rows_l, cols_l, w_l = [], [], []
        step = max(1, 40_000_000 // max(n_var * n_var * sym.shape[0], 1))
        for e in range(0, len(edge_pairs), step):
            ci = cand[ei[e : e + step]][:, :, None, :]
            cj = cand[ej[e : e + step]][:, None, :, :]
            ang = cls._disor(ci, cj, sym)
            if tolerance_deg > 0:
                weight = 0.5 * (1.0 + erf((threshold_deg - ang) / (tolerance_deg * _SQRT2)))
            else:
                weight = (ang <= threshold_deg).astype(np.float64)
            ke, va, vb = np.where(weight > min_weight)
            rows_l.append(ei[e : e + step][ke] * n_var + va)
            cols_l.append(ej[e : e + step][ke] * n_var + vb)
            w_l.append(weight[ke, va, vb])
        return np.concatenate(rows_l), np.concatenate(cols_l), np.concatenate(w_l)


class _DeviceProperty:
    """Report the device without probing CUDA at import — the driver probe can
    hang inside a frozen bundle, so it must never run at start-up."""

    def __get__(self, obj, owner):
        return "cuda" if quaternion_kernels.cuda_available() else "cpu"


class _NumbaQuaternions:
    """Accelerated backend: the same scalar kernels compiled for the GPU when one
    is present, else for the parallel CPU target.

    Kernels compile on first use, not at import, so start-up stays fast.
    """

    device = _DeviceProperty()

    @classmethod
    def multiply(cls, a, b) -> np.ndarray:
        return quaternion_kernels.kernels().multiply(a, b)

    @classmethod
    def disorientation_deg(cls, q1, q2, sym_quats) -> np.ndarray:
        return quaternion_kernels.kernels().disorientation_deg(q1, q2, sym_quats)

    @classmethod
    def candidate_parents(cls, variants, child) -> np.ndarray:
        return quaternion_kernels.kernels().candidate_parents(variants, child)

    @classmethod
    def best_variant(cls, variants, parent, child) -> np.ndarray:
        return quaternion_kernels.kernels().best_variant(variants, parent, child)

    @classmethod
    def fit_angles(cls, variants, parent, child, sym_quats) -> np.ndarray:
        return quaternion_kernels.kernels().fit_angles(variants, parent, child, sym_quats)

    @classmethod
    def pairwise_below(cls, quats, sym_quats, threshold_deg: float) -> np.ndarray:
        return quaternion_kernels.kernels().pairwise_below(quats, sym_quats, threshold_deg)

    @classmethod
    def variant_edges(
        cls, all_candidates, edge_pairs, sym_quats, threshold_deg, tolerance_deg, min_weight
    ):
        return quaternion_kernels.kernels().variant_edges(
            all_candidates, edge_pairs, sym_quats, threshold_deg, tolerance_deg, min_weight
        )


class _RustQuaternions(_NumbaQuaternions):
    """Compiled Rust kernels where they measured faster, numba for the rest.

    Only the operations Rust actually wins are overridden. On this hardware the
    O(N^2) pairwise comparison runs ~8x faster than the CUDA kernel, because it
    is launch/bandwidth-bound rather than FLOP-bound and Rust never materialises
    the (N, N, 24) intermediate.
    """

    device = "cpu (rust)"

    @classmethod
    def pairwise_below(cls, quats, sym_quats, threshold_deg: float) -> np.ndarray:
        return _rust.pairwise_below(
            np.ascontiguousarray(quats, dtype=np.float64),
            np.ascontiguousarray(sym_quats, dtype=np.float64),
            float(threshold_deg),
        )


def _select_backend():
    if os.environ.get("PAGB_DEVICE", "").strip().lower() == "cpu":
        return _NumpyQuaternions
    if _HAS_RUST:
        return _RustQuaternions
    return _NumbaQuaternions


Quaternions = _select_backend()
