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


def test_two_parameters_produce_the_full_grid(qtbot, synthetic_multi_parent):
    """Issue #10: several parameter sets (tolerance, threshold...) at once."""
    emap, _, _ = synthetic_multi_parent
    dlg = _dialog(qtbot, emap)
    for cb in dlg._preset_checks.values():
        cb.setChecked(False)
    dlg._sweep_check.setChecked(True)
    dlg._sweep_field.setCurrentText("tolerance_deg")
    dlg._sweep_values.setText("2, 3")
    dlg._sweep_check2.setChecked(True)
    dlg._sweep_field2.setCurrentText("merge_similar_deg")
    dlg._sweep_values2.setText("5, 7")

    named = dlg._named_configs()
    assert len(named) == 4, "both parameters must be crossed, not run separately"
    combos = {(c.tolerance_deg, c.merge_similar_deg) for _, c in named}
    assert combos == {(2.0, 5.0), (2.0, 7.0), (3.0, 5.0), (3.0, 7.0)}


def test_rank_selector_reorders_without_recomputing(qtbot, synthetic_multi_parent):
    from pagb_reconstruction.core.compare import ComparisonRun
    from pagb_reconstruction.core.fit_metrics import ReconstructionQuality

    def mk(name, fit, recon):
        q = ReconstructionQuality(
            n_parents=5, pct_reconstructed=recon, mean_fit_deg=fit, median_fit_deg=fit,
            fit_q25_deg=fit, fit_q75_deg=fit, fit_q95_deg=fit,
            area_weighted_ecd_um=10.0, mean_ecd_um=10.0, median_ecd_um=10.0,
        )
        return ComparisonRun(name=name, config=ReconstructionConfig(), result=None, quality=q)

    emap, _, _ = synthetic_multi_parent
    dlg = _dialog(qtbot, emap)
    runs = [mk("wide", 6.0, 95.0), mk("sliver", 1.0, 10.0)]
    dlg._rank_combo.setCurrentText("fit")
    dlg._populate_results(runs)
    assert dlg._runs[0].name == "sliver"
    dlg._rank_combo.setCurrentText("balanced")  # triggers re-rank
    assert dlg._runs[0].name == "wide"
