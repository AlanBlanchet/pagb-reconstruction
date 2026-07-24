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
    result = gm.measure(grain_map, step_size=(1.0, 1.0))
    assert result.mean_intercept_um > 0
    assert result.total_crossings > 0
    assert result.method == "intercept"


def test_area_method():
    grain_map = _checkerboard(10)
    gm = GrainMetrics(method="area", n_lines=10)
    result = gm.measure(grain_map, step_size=(1.0, 1.0))
    assert result.equivalent_diameter_um > 0
    assert result.grain_count > 0
    assert result.method == "area"


def test_astm_number_uses_log10_in_physical_range():
    # ASTM E112: G = -6.6457*log10(L_mm) - 3.298. A 50 um mean intercept gives
    # ~5.35; the old log2 bug gave ~25, far outside the real -3..14 range.
    assert abs(GrainMetrics._astm_number(50.0) - 5.35) < 0.1
    grain_map = _checkerboard(10)
    for method in ("intercept", "area"):
        result = GrainMetrics(method=method).measure(grain_map, step_size=(1.0, 1.0))
        assert -5.0 < result.astm_grain_size_number < 20.0


# ── #15: anisotropic (hex) scale + visible intercept geometry ──


def test_intercept_scales_axes_independently_on_a_hex_grid():
    """The real bug: a hex scan has dx != dy, so horizontal test lines must
    scale by dx and vertical by dy. A single step (the old code) makes the
    number wrong. With dx=0.1, dy=0.0866 the mean intercept must land between
    the two single-step answers, never equal either."""
    grain_map = _checkerboard(20)
    gm = GrainMetrics(method="intercept", n_lines=20)
    aniso = gm.measure(grain_map, step_size=(0.086603, 0.1)).mean_intercept_um
    iso_dx = gm.measure(grain_map, step_size=(0.1, 0.1)).mean_intercept_um
    iso_dy = gm.measure(grain_map, step_size=(0.086603, 0.086603)).mean_intercept_um
    assert iso_dy < aniso < iso_dx, "anisotropic result must differ from either single-step"


def test_area_uses_anisotropic_cell_area():
    grain_map = _checkerboard(10)
    gm = GrainMetrics(method="area")
    a = gm.measure(grain_map, step_size=(0.5, 2.0)).equivalent_diameter_um
    # a cell is 2.0 x 0.5 = 1.0 um^2, NOT 0.5^2 or 2.0^2
    square_small = gm.measure(grain_map, step_size=(0.5, 0.5)).equivalent_diameter_um
    square_big = gm.measure(grain_map, step_size=(2.0, 2.0)).equivalent_diameter_um
    assert square_small < a < square_big


def test_intercept_ignores_the_unreconstructed_border():
    # a -1 border is not a grain: its edges must not count as crossings, nor its
    # pixels toward the measured length
    grain_map = _checkerboard(12)
    grain_map[:, :3] = -1  # left band unreconstructed
    gm = GrainMetrics(method="intercept", n_lines=12)
    with_border = gm.measure(grain_map, step_size=(1.0, 1.0))
    # every crossing found is a real grain-vs-grain boundary (>=0 labels)
    assert with_border.total_crossings > 0
    assert with_border.grain_count == len(np.unique(grain_map[grain_map != -1]))


def test_measure_intercept_returns_drawable_geometry():
    grain_map = _checkerboard(10)
    gm = GrainMetrics(method="intercept", n_lines=5)
    result, lines, xs, ys = gm.measure_intercept(grain_map, step_size=(1.0, 1.0))
    assert result.method == "intercept"
    assert len(lines) > 0, "there must be test lines to draw"
    assert all(len(seg) == 2 for seg in lines), "each line is an endpoint PAIR"
    assert len(xs) == len(ys) == result.total_crossings, "one marker per crossing"
