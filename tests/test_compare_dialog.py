"""Compare-view dialog guards: config selection, ranked results, apply-chosen."""

import numpy as np

from pagb_reconstruction.core.compare import compare_configs
from pagb_reconstruction.core.reconstruction import ReconstructionConfig


def _dialog(qtbot, emap):
    from pagb_reconstruction.ui.widgets.compare_dialog import CompareDialog

    dlg = CompareDialog(emap, ReconstructionConfig())
    qtbot.addWidget(dlg)
    return dlg


def test_presets_and_sweep_build_named_configs(qtbot, synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    dlg = _dialog(qtbot, emap)
    # all four presets offered, at least one checked by default
    names = set(dlg._preset_checks)
    assert {"Default", "Fine", "Coarse", "Bainite"} <= names
    named = dlg._named_configs()
    assert len(named) >= 2, "default selection must compare at least two configs"
    # enabling the sweep adds one config per value
    dlg._sweep_check.setChecked(True)
    dlg._sweep_values.setText("0, 5, 10")
    with_sweep = dlg._named_configs()
    assert len(with_sweep) == len(named) + 3


def test_results_table_ranked_by_fit_and_apply(qtbot, synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    dlg = _dialog(qtbot, emap)
    runs = compare_configs(
        emap,
        [
            ("a", ReconstructionConfig(optimize_or=False, min_grain_size=2)),
            ("b", ReconstructionConfig(optimize_or=False, min_grain_size=3)),
        ],
    )
    dlg._populate_results(runs)
    assert dlg._table.rowCount() == 2
    # ranked by mean fit ascending (best first)
    fits = [
        float(dlg._table.item(r, 4).text().rstrip("°"))
        for r in range(dlg._table.rowCount())
    ]
    assert fits == sorted(fits)
    # applying the selected row emits the chosen run
    chosen = []
    dlg.run_chosen.connect(chosen.append)
    dlg._table.selectRow(0)
    dlg._apply_selected()
    assert len(chosen) == 1 and chosen[0].name in {"a", "b"}


def test_preview_crop_limits_map_size(qtbot, synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    dlg = _dialog(qtbot, emap)
    small = dlg._target_map(max_side=8)
    assert max(small.shape) <= 8
    full = dlg._target_map(max_side=10_000)
    assert full.shape == emap.shape
