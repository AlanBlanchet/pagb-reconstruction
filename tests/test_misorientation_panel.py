"""The misorientation histogram lives in its own dock, not the OR sidebar.

Two independent live measurements found the chart unreadable inside the OR
sidebar: it shares one QScrollArea with two text-heavy group boxes that consume
the viewport budget first, so at a 900px window only ~38px remained and no axis
or curve rendered at all. Raising the plot's own minimumHeight cannot fix that —
the constraint is total sidebar content vs viewport, not any one widget's floor.
So the chart gets a container with its own vertical budget.
"""


def test_histogram_is_not_in_the_or_sidebar(qtbot):
    from pagb_reconstruction.ui.widgets.or_panel import ORPanel

    panel = ORPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "_hist_plot"), (
        "the histogram must not share the OR sidebar's scroll area with the "
        "OR params and OR Details group boxes — they starve it of height"
    )


def test_misorientation_dock_exists_in_the_wide_bottom_group(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    assert "Misorientation" in w._docks, "misorientation chart needs its own dock"
    dock = w._docks["Misorientation"]
    assert dock in w._bottom_docks, (
        "it belongs in the bottom group, which is full-window width, not the "
        "380px right sidebar"
    )


def test_misorientation_panel_follows_the_selected_or(qtbot, sample_ebsd):
    from pagb_reconstruction.ui.widgets.misorientation_panel import MisorientationPanel

    panel = MisorientationPanel()
    qtbot.addWidget(panel)
    panel.set_ebsd_map(sample_ebsd)
    panel.set_or_type("NW")

    legend = panel._hist_plot.plotItem.legend
    labels = {item[1].text for item in legend.items}
    assert any("easured" in t for t in labels), f"measured curve unnamed: {labels}"
    assert any("NW" in t for t in labels), f"theoretical peaks not renamed: {labels}"
    assert len(legend.items) == 2, f"legend must hold exactly 2 entries, got {labels}"
