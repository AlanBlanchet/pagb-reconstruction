"""Manual correction of a reconstruction.

Automatic reconstruction gets most parents right and a few wrong. This gives the
operator the two things needed to fix the rest by hand: a ranked view of which
parents look incoherent (worst misfit first), and a way to reattach one parent to
another. Both work on a copy — the original result is never mutated, so a
correction can be undone by keeping the previous result.
"""

from dataclasses import dataclass

import numpy as np

from pagb_reconstruction.core.reconstruction import ReconstructionResult


@dataclass(frozen=True)
class ParentFit:
    """How well one reconstructed parent explains the pixels assigned to it."""

    parent_id: int
    n_pixels: int
    mean_fit_deg: float
    max_fit_deg: float


def parent_fit_summary(result: ReconstructionResult) -> list[ParentFit]:
    """Per-parent pixel count and misfit, for every reconstructed parent."""
    ids = np.asarray(result.parent_grain_ids)
    fits = np.asarray(result.fit_angles, dtype=np.float64)
    out: list[ParentFit] = []
    for pid in np.unique(ids[ids >= 0]):
        mask = ids == pid
        vals = fits[mask]
        vals = vals[np.isfinite(vals)]
        out.append(
            ParentFit(
                parent_id=int(pid),
                n_pixels=int(mask.sum()),
                mean_fit_deg=float(vals.mean()) if vals.size else float("nan"),
                max_fit_deg=float(vals.max()) if vals.size else float("nan"),
            )
        )
    return out


def worst_fit_parents(
    result: ReconstructionResult, limit: int = 20, min_pixels: int = 1
) -> list[ParentFit]:
    """Parents ranked worst-misfit first — the candidates to inspect or reattach.

    ``min_pixels`` filters out specks, which are noise rather than a parent worth
    correcting.
    """
    rows = [r for r in parent_fit_summary(result) if r.n_pixels >= min_pixels]
    rows.sort(key=lambda r: (-r.mean_fit_deg, -r.n_pixels))
    return rows[:limit]


def reassign_parent(
    result: ReconstructionResult, source_id: int, target_id: int
) -> ReconstructionResult:
    """Reattach every pixel of ``source_id`` to ``target_id``.

    The moved pixels adopt the target's parent orientation, and their misfit is
    re-measured against it — carrying the old fit over would misreport how good
    the correction actually is. Returns a new result; the input is unchanged.
    """
    ids = np.asarray(result.parent_grain_ids)
    if source_id == target_id:
        raise ValueError("source and target parent are the same")
    for pid in (source_id, target_id):
        if not (ids == pid).any():
            raise ValueError(f"no parent with id {pid} in this reconstruction")

    source_mask = ids == source_id
    target_quat = np.asarray(result.parent_orientations)[ids == target_id][0]

    new_ids = ids.copy()
    new_ids[source_mask] = target_id
    new_quats = np.asarray(result.parent_orientations).copy()
    new_quats[source_mask] = target_quat

    # Re-measure misfit for the moved pixels against their new parent.
    from pagb_reconstruction.utils.compute import Quaternions

    new_fits = np.asarray(result.fit_angles, dtype=np.float64).copy()
    moved = np.flatnonzero(source_mask)
    if moved.size:
        sym = np.array([[1.0, 0.0, 0.0, 0.0]])
        new_fits[moved] = Quaternions.disorientation_deg(
            new_quats[moved], np.repeat(target_quat[None, :], moved.size, axis=0), sym
        )

    return ReconstructionResult(
        parent_orientations=new_quats,
        parent_grain_ids=new_ids,
        fit_angles=new_fits,
        variant_ids=result.variant_ids,
        packet_ids=result.packet_ids,
        block_ids=result.block_ids,
        bain_ids=result.bain_ids,
        optimized_or=result.optimized_or,
    )
