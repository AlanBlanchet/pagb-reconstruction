"""Guards for the generic reconstruction quality metrics."""

import numpy as np

from pagb_reconstruction.core.fit_metrics import reconstruction_quality
from pagb_reconstruction.core.reconstruction import ReconstructionResult


def _result(parent_ids, fit):
    n = len(parent_ids)
    z = np.zeros(n, dtype=np.int32)
    return ReconstructionResult(
        parent_orientations=np.tile([1.0, 0, 0, 0], (n, 1)),
        parent_grain_ids=np.asarray(parent_ids, dtype=np.int32),
        fit_angles=np.asarray(fit, dtype=float),
        variant_ids=z,
        packet_ids=z,
        block_ids=z,
        bain_ids=z,
    )


def test_basic_counts_and_pct():
    # 8 px: 4 -> parent 0, 2 -> parent 1, 2 unreconstructed (-1)
    res = _result([0, 0, 0, 0, 1, 1, -1, -1], [1.0] * 6 + [np.nan] * 2)
    q = reconstruction_quality(res, step_size_um=(1.0, 1.0))
    assert q.n_parents == 2
    assert abs(q.pct_reconstructed - 75.0) < 1e-6
    assert abs(q.mean_fit_deg - 1.0) < 1e-6


def test_area_weighted_ecd_favours_large_grain():
    # parent 0 = 100 px, parent 1 = 1 px, 1 µm step.
    ids = [0] * 100 + [1]
    res = _result(ids, [2.0] * 101)
    q = reconstruction_quality(res, step_size_um=(1.0, 1.0))
    d_big = np.sqrt(4.0 * 100 / np.pi)
    # area-weighted ECD is pulled toward the big grain, well above the arithmetic mean
    assert q.area_weighted_ecd_um > q.mean_ecd_um
    assert abs(q.area_weighted_ecd_um - d_big) < 0.5


def test_empty_reconstruction_is_safe():
    res = _result([-1, -1, -1], [np.nan, np.nan, np.nan])
    q = reconstruction_quality(res, step_size_um=(0.3, 0.3))
    assert q.n_parents == 0
    assert q.pct_reconstructed == 0.0
    assert q.area_weighted_ecd_um == 0.0
