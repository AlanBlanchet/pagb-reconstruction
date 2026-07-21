"""Grain-size measurement must work on sparse grids too.

Issue #11: "L'outil measure ne marche pas". The measurement reshaped the flat
per-pixel parent ids straight into (rows, cols). On any scan where the measured
points do not fill the grid — every hexagonal scan — that raises ValueError
inside a Qt slot, which Qt swallows, so the button silently did nothing.
"""

import numpy as np


def _sparse_map():
    """A map whose measured points do not fill its grid (like a hex scan)."""
    from orix.crystal_map import CrystalMap, Phase, PhaseList
    from orix.quaternion import Rotation

    from pagb_reconstruction.core.ebsd_map import EBSDMap
    from pagb_reconstruction.core.phase import PhaseConfig
    from pagb_reconstruction.io.grid_header import GridInfo

    n_rows, n_cols = 6, 8
    xs, ys = [], []
    for r in range(n_rows):
        count = n_cols if r % 2 == 0 else n_cols - 1  # short even rows
        offset = 0.0 if r % 2 == 0 else 0.5
        for c in range(count):
            xs.append(offset + c)
            ys.append(r * 0.866)
    n = len(xs)
    xmap = CrystalMap(
        rotations=Rotation.from_axes_angles([[0, 0, 1]] * n, np.linspace(0, 1, n)),
        phase_id=np.zeros(n, dtype=int),
        x=np.array(xs, dtype=float),
        y=np.array(ys, dtype=float),
        phase_list=PhaseList(Phase(name="ferrite", point_group="m-3m")),
    )
    grid = GridInfo(n_rows=n_rows, n_cols=n_cols, dx=1.0, dy=0.866, hexagonal=True)
    return EBSDMap(
        crystal_map=xmap, phases=[PhaseConfig.austenite()], grid=grid
    )


def _result_for(emap):
    from pagb_reconstruction.core.reconstruction import ReconstructionResult

    n = emap.crystal_map.size
    z = np.zeros(n, dtype=np.int32)
    return ReconstructionResult(
        parent_orientations=np.tile([1.0, 0, 0, 0], (n, 1)),
        parent_grain_ids=(np.arange(n, dtype=np.int32) % 4),
        fit_angles=np.zeros(n),
        variant_ids=z, packet_ids=z, block_ids=z, bain_ids=z,
    )


def test_sparse_map_really_is_sparse():
    emap = _sparse_map()
    rows, cols = emap.shape
    assert emap.is_sparse, "precondition: measured points must not fill the grid"
    assert emap.crystal_map.size != rows * cols


def test_measurement_runs_on_sparse_map(qtbot):
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard

    emap = _sparse_map()
    result = _result_for(emap)

    dash = StatsDashboard()
    qtbot.addWidget(dash)
    dash._ebsd_map = emap
    dash._result = result
    dash._run_measurement()  # must not raise

    text = dash._metrics_label.text()
    assert "Mean intercept" in text
    assert "ASTM" in text
