"""OR sidebar — controls and derived OR details.

The misorientation histogram used to live here and is now its own dock; see
tests/test_misorientation_panel.py for why. What remains is a control panel, so
what matters is that the derived OR details actually track the selected preset.
"""


def _panel(qtbot):
    from pagb_reconstruction.ui.widgets.or_panel import ORPanel

    panel = ORPanel()
    qtbot.addWidget(panel)
    return panel


def test_details_track_the_selected_preset(qtbot):
    from pagb_reconstruction.core.orientation_relationship import (
        OrientationRelationship,
    )

    panel = _panel(qtbot)
    seen = set()
    for name in OrientationRelationship.preset_names():
        panel._or_combo.setCurrentText(name)
        assert panel.get_or_type() == name
        # rotation angle is derived from the preset, so it must not go stale
        angle = panel._angle_label.text()
        assert angle.endswith("°") and angle != "-", f"{name}: no angle shown"
        seen.add((name, angle, panel._variant_count_label.text()))

    assert len({a for _, a, _ in seen}) > 1, (
        "every preset reported the same rotation angle — details are not "
        "recomputed on selection"
    )


def test_optimize_toggle_is_exposed(qtbot):
    panel = _panel(qtbot)
    assert panel.get_optimize() is True, "OR optimisation defaults on"
    panel._optimize_cb.setChecked(False)
    assert panel.get_optimize() is False
