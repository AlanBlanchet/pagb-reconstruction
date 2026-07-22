"""The misorientation spectrum is a plot in the Statistics BROWSER now.

It (and the pole figure) used to each own a cramped bottom dock; Alan asked to
stop making things "squishy and tight", so both fold into the Statistics browser
where a selected plot owns the whole panel. It stays out of the OR sidebar (two
live measurements found it unreadable there — starved of height by two text-heavy
group boxes in one shared scroll area).
"""


def test_histogram_is_not_in_the_or_sidebar(qtbot):
    from pagb_reconstruction.ui.widgets.or_panel import ORPanel

    panel = ORPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "_hist_plot"), (
        "the histogram must not share the OR sidebar's scroll area with the "
        "OR params and OR Details group boxes — they starve it of height"
    )


def test_spectrum_is_a_browser_plot_not_its_own_dock(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow
    from pagb_reconstruction.ui.widgets.stat_plots import CATALOG

    w = MainWindow()
    qtbot.addWidget(w)

    assert "Misorientation" not in w._docks, "spectrum is folded into the browser"
    assert any(e.key == "spectrum" for e in CATALOG), "spectrum is a catalog plot"


def test_spectrum_plot_does_not_wheel_zoom(qtbot):
    """Alan: 'we can scroll for each stat plot ... Very weird.' The spectrum's
    bare PlotWidget zoomed on wheel; it must be inert now."""
    from pagb_reconstruction.ui.widgets.misorientation_panel import MisorientationPanel

    panel = MisorientationPanel()
    qtbot.addWidget(panel)
    vb = panel._hist_plot.getPlotItem().getViewBox()
    assert list(vb.state["mouseEnabled"]) == [False, False], "spectrum must not zoom"


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
