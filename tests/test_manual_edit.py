"""Issue #10: find incoherent / poor-fit parents and reattach them by hand.

"mettre en évidence les parents que je trouves incohérent et que je puisse dire
à quels grains parents les rattacher. Ou alors ceux avec un faible fit pour
essayer de minimiser les misfit."
"""

import numpy as np
import pytest

from pagb_reconstruction.core.manual_edit import (
    parent_fit_summary,
    reassign_parent,
    worst_fit_parents,
)
from pagb_reconstruction.core.reconstruction import ReconstructionResult


def _result():
    # 3 parents: 0 fits well, 1 fits badly, 2 is tiny
    pids = np.array([0, 0, 0, 0, 1, 1, 1, 2], dtype=np.int32)
    fits = np.array([0.5, 0.4, 0.6, 0.5, 9.0, 8.0, 10.0, 2.0])
    quats = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (pids.size, 1))
    quats[pids == 1] = [0.0, 1.0, 0.0, 0.0]
    z = np.zeros(pids.size, dtype=np.int32)
    return ReconstructionResult(
        parent_orientations=quats, parent_grain_ids=pids, fit_angles=fits,
        variant_ids=z, packet_ids=z, block_ids=z, bain_ids=z,
    )


def test_summary_reports_size_and_fit_per_parent():
    rows = {r.parent_id: r for r in parent_fit_summary(_result())}
    assert set(rows) == {0, 1, 2}
    assert rows[0].n_pixels == 4
    assert rows[1].n_pixels == 3
    assert rows[0].mean_fit_deg == pytest.approx(0.5, abs=0.05)
    assert rows[1].mean_fit_deg == pytest.approx(9.0, abs=0.05)


def test_worst_fit_parents_surfaces_the_incoherent_one_first():
    worst = worst_fit_parents(_result(), limit=2)
    assert [r.parent_id for r in worst] == [1, 2]


def test_worst_fit_ignores_parents_below_min_size():
    # the tiny parent is noise, not something worth reattaching
    worst = worst_fit_parents(_result(), limit=5, min_pixels=3)
    assert [r.parent_id for r in worst] == [1, 0]


def test_reassign_moves_pixels_and_adopts_target_orientation():
    res = _result()
    updated = reassign_parent(res, source_id=1, target_id=0)

    assert not (updated.parent_grain_ids == 1).any(), "source parent still present"
    assert (updated.parent_grain_ids == 0).sum() == 7
    moved = res.parent_grain_ids == 1
    assert np.allclose(
        updated.parent_orientations[moved], res.parent_orientations[res.parent_grain_ids == 0][0]
    ), "reattached pixels must take the target parent's orientation"
    # the original result is untouched
    assert (res.parent_grain_ids == 1).sum() == 3


def test_reassign_recomputes_fit_against_the_new_parent():
    res = _result()
    updated = reassign_parent(res, source_id=1, target_id=0)
    moved = res.parent_grain_ids == 1
    # fit is re-measured, not carried over from the old parent
    assert not np.allclose(updated.fit_angles[moved], res.fit_angles[moved])


def test_reassign_rejects_unknown_parent():
    with pytest.raises(ValueError):
        reassign_parent(_result(), source_id=99, target_id=0)
