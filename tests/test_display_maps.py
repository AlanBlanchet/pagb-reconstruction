"""Display-map regressions from the field (issue #8): non-indexed points must
not speckle the carto black, and unreconstructed pixels must never wear a
parent colour."""
import numpy as np
import pytest

from pagb_reconstruction.core.reconstruction import ReconstructionResult


NEUTRAL = 0.18


def test_nonindexed_points_are_filled_in_display_maps(synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    # Simulate a poorly-indexed scan: mark a scatter of points non-indexed.
    rng = np.random.default_rng(7)
    n = emap.crystal_map.size
    knock = rng.choice(n, size=n // 5, replace=False)
    # orix's phase_id property returns a copy — write the backing array
    # (the library exposes no mutator for point re-classification).
    phase_id = emap.crystal_map._phase_id
    original = phase_id[knock].copy()
    phase_id[knock] = -1
    try:
        ipf = emap.ipf_map()
        grid_mask = emap.indexed_grid_mask
        assert not grid_mask.all(), "test setup: some points must be non-indexed"
        # Non-indexed pixels take a neighbour's colour — none stay pure black.
        black = np.all(ipf == 0, axis=-1)
        assert not black[~grid_mask].any(), "non-indexed points rendered as black specks"
    finally:
        phase_id[knock] = original


def test_parent_boundary_map_paints_unreconstructed_neutral(synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    n = emap.crystal_map.size
    ids = np.full(n, -1, dtype=int)
    ids[: n // 50] = 0  # a near-empty result: 2% reconstructed, one parent
    emap.set_result(
        ReconstructionResult(
            parent_orientations=np.tile([1.0, 0, 0, 0], (n, 1)),
            parent_grain_ids=ids,
            fit_angles=np.zeros(n),
            variant_ids=np.zeros(n, dtype=int),
            packet_ids=np.zeros(n, dtype=int),
            block_ids=np.zeros(n, dtype=int),
            bain_ids=np.zeros(n, dtype=int),
        )
    )
    try:
        rgb = emap.parent_boundary_map()
        grid_ids = emap._to_grid(ids, fill=-1)
        unrec = grid_ids < 0
        # Every unreconstructed pixel is the neutral grey (or a black boundary
        # line) — never a tab20 parent colour spanning the whole map.
        px = rgb[unrec]
        is_neutral = np.all(np.isclose(px, NEUTRAL), axis=-1)
        is_boundary = np.all(px == 0.0, axis=-1)
        assert np.all(is_neutral | is_boundary), "unreconstructed pixels wear a parent colour"
    finally:
        emap.set_result(None)
