"""Device-aware batched quaternion algebra (GPU when available).

The reconstruction hot loops are batched quaternion operations — variant/parent
products, symmetry-reduced disorientations, pairwise parent comparisons. This
module runs them in torch on the compute device: the GPU when one is present
(a large win for the O(N²) and edge-graph passes), the CPU otherwise. Public
methods take and return numpy arrays; tensors live on ``device`` for the maths.

float32 is used on device (consumer GPUs run float64 at ~1/32 rate); the
resulting angle error is ~1e-3° — far below the degrees-scale reconstruction
thresholds.
"""

import os

import numpy as np
import torch


def _resolve_device() -> torch.device:
    override = os.environ.get("PAGB_DEVICE", "").strip()
    if override:
        return torch.device(override)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


_SQRT2 = float(np.sqrt(2.0))


class Quaternions:
    """Batched quaternion algebra on :attr:`device`. Stateless — the device is
    resolved once at import (cuda if present, else cpu; override PAGB_DEVICE)."""

    device: torch.device = _resolve_device()
    dtype: torch.dtype = torch.float32

    @classmethod
    def _t(cls, a: np.ndarray) -> torch.Tensor:
        return torch.as_tensor(
            np.ascontiguousarray(a), dtype=cls.dtype, device=cls.device
        )

    @staticmethod
    def _mul(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
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
    def _conj(q: torch.Tensor) -> torch.Tensor:
        return q * q.new_tensor([1.0, -1.0, -1.0, -1.0])

    @classmethod
    def _disor(cls, q1: torch.Tensor, q2: torch.Tensor, sym: torch.Tensor) -> torch.Tensor:
        # one-sided symmetry-reduced disorientation angle (deg), reducing the
        # trailing sym axis — matches the numba _misori_angle_simple.
        mori = cls._mul(q1, cls._conj(q2))
        equiv_w = cls._mul(sym, mori.unsqueeze(-2))[..., 0]
        w = equiv_w.abs().clamp(max=1.0)
        return torch.rad2deg(2.0 * torch.arccos(w)).amin(dim=-1)

    # ── numpy-facing operations ──
    @classmethod
    def multiply(cls, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return cls._mul(cls._t(a), cls._t(b)).cpu().numpy()

    @classmethod
    def disorientation_deg(
        cls, q1: np.ndarray, q2: np.ndarray, sym_quats: np.ndarray
    ) -> np.ndarray:
        return cls._disor(cls._t(q1), cls._t(q2), cls._t(sym_quats)).cpu().numpy()

    @classmethod
    def candidate_parents(cls, variants: np.ndarray, child: np.ndarray) -> np.ndarray:
        """(K,4) variants, (n,4) children → (n,K,4) candidate parents
        (~variant ∘ child), sign-normalised to w ≥ 0."""
        v = cls._t(variants)
        c = cls._t(child)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])
        cand = cand * torch.where(cand[..., :1] < 0, -1.0, 1.0)
        return cand.cpu().numpy()

    @classmethod
    def best_variant(
        cls, variants: np.ndarray, parent: np.ndarray, child: np.ndarray
    ) -> np.ndarray:
        """Per grain, the variant index minimising the raw disorientation between
        the predicted child (variant ∘ parent) and the measured child."""
        v = cls._t(variants)
        p = cls._t(parent)
        c = cls._t(child)
        predicted = cls._mul(v[None, :, :], p[:, None, :])
        mori = cls._mul(cls._conj(predicted), c[:, None, :])
        return torch.argmax(mori[..., 0].abs(), dim=1).cpu().numpy().astype(np.int32)

    @classmethod
    def fit_angles(
        cls,
        variants: np.ndarray,
        parent: np.ndarray,
        child: np.ndarray,
        sym_quats: np.ndarray,
    ) -> np.ndarray:
        """Per grain, the closest candidate-parent disorientation (deg) to the
        assigned parent — the reconstruction fit angle."""
        v = cls._t(variants)
        p = cls._t(parent)
        c = cls._t(child)
        sym = cls._t(sym_quats)
        cand = cls._mul(cls._conj(v)[None, :, :], c[:, None, :])  # (n,K,4)
        dev = cls._disor(cand, p[:, None, :], sym)  # (n,K)
        return dev.amin(dim=1).cpu().numpy()

    @classmethod
    def _row_chunk(cls, n_inner: int) -> int:
        """Rows per chunk so an ``(rows, n_inner, 4)`` intermediate stays within
        a ~1 GB device budget (bounds GPU memory on large maps)."""
        return max(1, 1_000_000_000 // (max(n_inner, 1) * 4 * 8))

    @classmethod
    def pairwise_below(
        cls, quats: np.ndarray, sym_quats: np.ndarray, threshold_deg: float
    ) -> np.ndarray:
        """Upper-triangular bool matrix: (i,j) True iff disorientation(i,j) <
        threshold. GPU-accelerated O(N²), chunked over rows — the parent-merge
        comparison."""
        q = cls._t(quats)
        sym = cls._t(sym_quats)
        n, s = q.shape[0], sym.shape[0]
        out = np.zeros((n, n), dtype=bool)
        step = cls._row_chunk(n * s)
        for r in range(0, n, step):
            dmat = cls._disor(q[r : r + step, None, :], q[None, :, :], sym)
            # keep only global j > i: within the chunk, col j vs local row li
            # (global r+li) → diagonal offset r+1.
            below = torch.triu(dmat < threshold_deg, diagonal=r + 1)
            out[r : r + step] = below.cpu().numpy()
        return out

    @classmethod
    def variant_edges(
        cls,
        all_candidates: np.ndarray,
        edge_pairs: np.ndarray,
        sym_quats: np.ndarray,
        threshold_deg: float,
        tolerance_deg: float,
        min_weight: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Variant-graph edges: for every adjacent grain pair, the Gaussian edge
        weight between each candidate-parent pair, kept when > ``min_weight``.
        Returns (rows, cols, weights) as flat variant-node index arrays."""
        cand = cls._t(all_candidates)  # (G, K, 4)
        sym = cls._t(sym_quats)
        n_var = cand.shape[1]
        ei = torch.as_tensor(edge_pairs[:, 0], device=cls.device)
        ej = torch.as_tensor(edge_pairs[:, 1], device=cls.device)
        # chunk over edges: the (chunk, K, K, S, 4) intermediate would be many GB
        # for a full map, so bound it to a ~1 GB device budget.
        step = cls._row_chunk(n_var * n_var * sym.shape[0])
        rows_l, cols_l, w_l = [], [], []
        for e in range(0, ei.shape[0], step):
            ci = cand[ei[e : e + step]][:, :, None, :]  # (c, K, 1, 4)
            cj = cand[ej[e : e + step]][:, None, :, :]  # (c, 1, K, 4)
            ang = cls._disor(ci, cj, sym)  # (c, K, K)
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
