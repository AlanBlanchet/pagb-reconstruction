"""Device-aware batched quaternion algebra — GPU (torch) when available, numpy
otherwise.

The reconstruction hot loops are batched quaternion operations: variant/parent
products, symmetry-reduced disorientations, pairwise parent comparisons, the
variant-edge graph. On a machine with torch + a GPU these run on the GPU (a
large win for the O(N²) and edge passes); torch on CPU is used if present; and
if torch is not installed at all — e.g. the lean frozen desktop build, which
must not carry torch's ~700 MB for a user with no GPU — a numpy backend runs the
identical maths on the CPU.

The public class is :data:`Quaternions`, bound at import to whichever backend is
available. Methods take and return numpy arrays; the backend is transparent.
float32 is used on the GPU (consumer cards run float64 at ~1/32 rate); the
angle error is ~1e-3°, far below the degrees-scale reconstruction thresholds.
"""

import os

import numpy as np

try:
    import torch

    _HAS_TORCH = True
except ImportError:  # lean build / no torch — fall back to numpy on the CPU
    _HAS_TORCH = False

_SQRT2 = float(np.sqrt(2.0))


class _NumpyQuaternions:
    """CPU quaternion algebra in numpy — the fallback when torch is absent."""

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


def _resolve_device() -> "torch.device":
    override = os.environ.get("PAGB_DEVICE", "").strip()
    if override:
        return torch.device(override)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class _TorchQuaternions:
    """GPU-capable quaternion algebra in torch (used when torch is installed)."""

    device = _resolve_device() if _HAS_TORCH else "cpu"
    dtype = torch.float32 if _HAS_TORCH else None

    @classmethod
    def _t(cls, a: np.ndarray) -> "torch.Tensor":
        return torch.as_tensor(np.ascontiguousarray(a), dtype=cls.dtype, device=cls.device)

    @staticmethod
    def _mul(a, b):
        aw, ax, ay, az = a.unbind(-1)
        bw, bx, by, bz = b.unbind(-1)
        return torch.stack(
            (
                aw * bw - ax * bx - ay * by - az * bz,
                aw * bx + ax * bw + ay * bz - az * by,
                aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw,
            ),
            dim=-1,
        )

    @staticmethod
    def _conj(q):
        return q * q.new_tensor([1.0, -1.0, -1.0, -1.0])

    @classmethod
    def _disor(cls, q1, q2, sym):
        mori = cls._mul(q1, cls._conj(q2))
        equiv_w = cls._mul(sym, mori.unsqueeze(-2))[..., 0]
        w = equiv_w.abs().clamp(max=1.0)
        return torch.rad2deg(2.0 * torch.arccos(w)).amin(dim=-1)

    @classmethod
    def multiply(cls, a, b):
        return cls._mul(cls._t(a), cls._t(b)).cpu().numpy()

    @classmethod
    def disorientation_deg(cls, q1, q2, sym_quats):
        return cls._disor(cls._t(q1), cls._t(q2), cls._t(sym_quats)).cpu().numpy()

    @classmethod
    def candidate_parents(cls, variants, child):
        v, c = cls._t(variants), cls._t(child)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])
        cand = cand * torch.where(cand[..., :1] < 0, -1.0, 1.0)
        return cand.cpu().numpy()

    @classmethod
    def best_variant(cls, variants, parent, child):
        v, p, c = cls._t(variants), cls._t(parent), cls._t(child)
        predicted = cls._mul(v[None, :, :], p[:, None, :])
        mori = cls._mul(cls._conj(predicted), c[:, None, :])
        return torch.argmax(mori[..., 0].abs(), dim=1).cpu().numpy().astype(np.int32)

    @classmethod
    def fit_angles(cls, variants, parent, child, sym_quats):
        v, p, c, sym = cls._t(variants), cls._t(parent), cls._t(child), cls._t(sym_quats)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])
        return cls._disor(cand, p[:, None, :], sym).amin(dim=1).cpu().numpy()

    @classmethod
    def _row_chunk(cls, n_inner: int) -> int:
        return max(1, 1_000_000_000 // (max(n_inner, 1) * 4 * 8))

    @classmethod
    def pairwise_below(cls, quats, sym_quats, threshold_deg: float):
        q, sym = cls._t(quats), cls._t(sym_quats)
        n, s = q.shape[0], sym.shape[0]
        out = np.zeros((n, n), dtype=bool)
        step = cls._row_chunk(n * s)
        for r in range(0, n, step):
            dmat = cls._disor(q[r : r + step, None, :], q[None, :, :], sym)
            out[r : r + step] = torch.triu(dmat < threshold_deg, diagonal=r + 1).cpu().numpy()
        return out

    @classmethod
    def variant_edges(
        cls, all_candidates, edge_pairs, sym_quats, threshold_deg, tolerance_deg, min_weight
    ):
        cand = cls._t(all_candidates)
        sym = cls._t(sym_quats)
        n_var = cand.shape[1]
        ei = torch.as_tensor(edge_pairs[:, 0], device=cls.device)
        ej = torch.as_tensor(edge_pairs[:, 1], device=cls.device)
        step = cls._row_chunk(n_var * n_var * sym.shape[0])
        rows_l, cols_l, w_l = [], [], []
        for e in range(0, ei.shape[0], step):
            ci = cand[ei[e : e + step]][:, :, None, :]
            cj = cand[ej[e : e + step]][:, None, :, :]
            ang = cls._disor(ci, cj, sym)
            if tolerance_deg > 0:
                weight = 0.5 * (1.0 + torch.erf((threshold_deg - ang) / (tolerance_deg * _SQRT2)))
            else:
                weight = (ang <= threshold_deg).to(cls.dtype)
            keep = weight > min_weight
            e_idx, va, vb = torch.where(keep)
            rows_l.append((ei[e : e + step][e_idx] * n_var + va).cpu().numpy())
            cols_l.append((ej[e : e + step][e_idx] * n_var + vb).cpu().numpy())
            w_l.append(weight[keep].cpu().numpy().astype(np.float64))
        return np.concatenate(rows_l), np.concatenate(cols_l), np.concatenate(w_l)


Quaternions = _TorchQuaternions if _HAS_TORCH else _NumpyQuaternions
