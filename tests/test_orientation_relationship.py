"""Physics ground-truth tests for the orientation relationship.

These deliberately avoid a self-referential round-trip (generate children with
``variant_quaternions`` then invert with the same set), which passes regardless
of whether the variant set is physically correct. Instead they check the variant
set against the PUBLISHED Kurdjumov-Sachs 24-variant misorientation spectrum
(Morito et al., Acta Materialia 51 (2003) 1789) — the check that catches a
degenerate variant set (the c803ce5 regression: ``or_ori * ps`` made all 24
variants symmetry-equivalent, so reconstruction returned dust).
"""

import numpy as np
import pytest

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.utils.math_ops import MisorientationOps

# Kurdjumov-Sachs inter-variant disorientation angles (deg), the well-known
# spectrum reproduced across the literature and MTEX's MartensiteVariants docs.
KS_SPECTRUM = np.array(
    [10.53, 14.88, 20.61, 21.06, 47.11, 49.47, 50.51, 51.73, 57.21, 60.0]
)


def _variant_pair_angles(orr: OrientationRelationship) -> np.ndarray:
    variants = orr.variant_quaternions()
    sym = np.ascontiguousarray(orr.child_phase.symmetry.data, dtype=np.float64)
    n = len(variants)
    angles = []
    for i in range(n):
        for j in range(i + 1, n):
            angles.append(
                MisorientationOps._angle_with_symmetry(
                    np.ascontiguousarray(variants[i], dtype=np.float64),
                    np.ascontiguousarray(variants[j], dtype=np.float64),
                    sym,
                )
            )
    return np.array(angles)


def test_ks_has_24_distinct_variants():
    orr = OrientationRelationship.from_preset("KS")
    assert orr.n_variants == 24, f"KS must have 24 variants, got {orr.n_variants}"


def test_ks_variant_spectrum_matches_literature():
    """Every KS variant-pair disorientation must land on a known KS special
    angle. A degenerate variant set (all symmetry-equivalent) instead yields
    only the cubic symmetry angles 60/90/120/180 and fails here."""
    orr = OrientationRelationship.from_preset("KS")
    angles = _variant_pair_angles(orr)
    observed = np.unique(np.round(angles, 1))

    # The degenerate-variant failure signature: pure symmetry angles, no KS peak.
    assert not np.all(np.isin(observed, [0.0, 60.0, 90.0, 120.0, 180.0])), (
        f"variant set is degenerate (only symmetry angles {observed}); "
        "variants are symmetry-equivalent, not distinct KS variants"
    )

    # Each observed peak must match a literature KS angle within 1 deg.
    for a in observed:
        assert np.min(np.abs(KS_SPECTRUM - a)) < 1.0, (
            f"variant-pair angle {a} deg is not a KS special angle {KS_SPECTRUM}"
        )
    # And the hallmark low-angle KS peaks must be present (absent when degenerate).
    for expected in (10.53, 49.47, 60.0):
        assert np.min(np.abs(angles - expected)) < 1.0, (
            f"KS spectrum peak {expected} deg missing from variant set"
        )


def test_candidate_parents_invert_predicted_child():
    """A child synthesised as one variant of a known parent must yield that
    parent back among its candidates — the forward/inverse pair must agree."""
    from orix.quaternion import Orientation

    orr = OrientationRelationship.from_preset("KS")
    variants = orr.variant_quaternions()
    parent = Orientation.random()
    parent_q = parent.data.flatten()
    if parent_q[0] < 0:
        parent_q = -parent_q

    sym = np.ascontiguousarray(orr.parent_phase.symmetry.data, dtype=np.float64)
    for v in variants[:5]:
        # predicted_child = variant ∘ parent (reconstruction._compute_variants:
        # `v_ori * parent_ori`), inverted by candidate_parents' (~variant) * child.
        child = (Orientation(v.reshape(1, 4)) * parent).data.flatten()
        candidates = orr.candidate_parents(child)
        dev = min(
            MisorientationOps._angle_with_symmetry(
                np.ascontiguousarray(c, dtype=np.float64),
                np.ascontiguousarray(parent_q, dtype=np.float64),
                sym,
            )
            for c in candidates
        )
        assert dev < 1.0, f"true parent not recovered (best {dev:.1f} deg off)"


def test_ks_variant_merge_groups_pair_up():
    """Hielscher et al. 2022 §5.4: KS variants merge 24→12 by pairing variants
    whose candidate-parent orientations are within δ=8.5° (the V1–V4 block
    pairing) — a 4× edge reduction for the variant graph."""
    orr = OrientationRelationship.from_preset("KS")
    groups = orr.variant_merge_groups(12.0)
    assert len(groups) == 12, f"KS must merge into 12 groups, got {len(groups)}"
    assert all(len(g) == 2 for g in groups), "each KS group must be a variant pair"
    # every variant appears exactly once
    flat = sorted(i for g in groups for i in g)
    assert flat == list(range(orr.n_variants))


def test_merge_groups_disabled_is_identity():
    orr = OrientationRelationship.from_preset("KS")
    groups = orr.variant_merge_groups(0.0)
    assert len(groups) == orr.n_variants
    assert all(len(g) == 1 for g in groups)


def test_candidate_parents_batch_matches_per_grain():
    """The batched candidate-parent builder must match the per-grain
    candidate_parents exactly — it replaces the orix loop in build_variant_graph."""
    orr = OrientationRelationship.from_preset("KS")
    rng = np.random.default_rng(0)
    child = rng.standard_normal((7, 4))
    child /= np.linalg.norm(child, axis=1, keepdims=True)
    batch = orr.candidate_parents_batch(child)
    assert batch.shape == (7, orr.n_variants, 4)
    for i in range(7):
        ref = orr.candidate_parents(child[i])
        assert np.allclose(batch[i], ref, atol=1e-10), f"grain {i} mismatch"
