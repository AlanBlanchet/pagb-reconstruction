import numpy as np

from pagb_reconstruction.core.grain_metrics import GrainMetrics


def _checkerboard(n: int = 10) -> np.ndarray:
    grid = np.zeros((n, n), dtype=np.int32)
    label = 0
    for r in range(0, n, 2):
        for c in range(0, n, 2):
            grid[r : r + 2, c : c + 2] = label
            label += 1
    return grid


def test_intercept_method():
    grain_map = _checkerboard(10)
    gm = GrainMetrics(method="intercept", n_lines=10)
    result = gm.measure(grain_map, step_size=1.0)
    assert result.mean_intercept_um > 0
    assert result.total_crossings > 0
    assert result.method == "intercept"


def test_area_method():
    grain_map = _checkerboard(10)
    gm = GrainMetrics(method="area", n_lines=10)
    result = gm.measure(grain_map, step_size=1.0)
    assert result.equivalent_diameter_um > 0
    assert result.grain_count > 0
    assert result.method == "area"


def test_astm_number_range():
    grain_map = _checkerboard(10)
    for method in ("intercept", "area"):
        gm = GrainMetrics(method=method)
        result = gm.measure(grain_map, step_size=1.0)
        assert np.isfinite(result.astm_grain_size_number)
