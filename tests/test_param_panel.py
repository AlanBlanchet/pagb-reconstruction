"""Reconstruction parameter panel guards.

The panel is built generically from ReconstructionConfig.model_fields, so a new
field must be listed in _FIELD_GROUPS to appear. These guard the controls Eloïse
asked for: a minimum-grain-size control and a bainite preset.
"""


def test_min_parent_size_control_is_exposed(qtbot):
    from pagb_reconstruction.ui.widgets.param_panel import ParamPanel, _FIELD_GROUPS

    grouped = [f for fields in _FIELD_GROUPS.values() for f in fields]
    assert "min_parent_size_um" in grouped, "min grain-size control must be in a group"
    panel = ParamPanel()
    qtbot.addWidget(panel)
    assert "min_parent_size_um" in panel._field_widgets, "control must render"


def test_size_controls_have_clear_unit_labels():
    """The four size controls must carry disambiguating unit labels, not raw
    snake_case (a metallurgist should not see the stray word 'Um')."""
    from pagb_reconstruction.core.reconstruction import ReconstructionConfig

    titles = {
        "min_parent_size_um": "Min. parent grain size (µm)",
        "min_grain_size": "Min. child grain (px)",
        "min_cluster_size": "Min. cluster size (grains)",
        "merge_inclusions_max_size": "Merge islands ≤ (px)",
    }
    for field, expected in titles.items():
        assert ReconstructionConfig.model_fields[field].title == expected


def test_set_config_syncs_preset_selection(qtbot):
    """Applying a config (e.g. a Compare winner) must sync the preset tabs:
    a matching preset gets highlighted, a custom config deselects all — else
    the highlighted tab lies and clicking it silently resets the values."""
    from pagb_reconstruction.ui.widgets.param_panel import _PRESETS, ParamPanel

    panel = ParamPanel()
    qtbot.addWidget(panel)
    panel.set_config(_PRESETS["Fine"])
    assert panel._preset_control.current_text() == "Fine"
    custom = _PRESETS["Fine"].model_copy(update={"threshold_deg": 3.33})
    panel.set_config(custom)
    assert panel._preset_control.current_text() is None, (
        "custom config must deselect every preset tab"
    )


def test_bainite_preset_exists_and_is_looser(qtbot):
    from pagb_reconstruction.ui.widgets.param_panel import _PRESETS

    assert "Bainite" in _PRESETS, "a Bainite preset must exist (primary use case)"
    bainite = _PRESETS["Bainite"]
    default = _PRESETS["Default"]
    # Bainite has weak variant selection -> wider lath spread -> looser grouping.
    assert bainite.threshold_deg >= default.threshold_deg
    assert bainite.min_parent_size_um > 0
