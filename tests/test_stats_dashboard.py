"""Statistics — a plot BROWSER: a grouped selector + one large focused plot.

The old dashboard crammed four charts into one grid row and the pole figure +
spectrum sat in their own tiny docks. Now one spacious browser holds them all,
each plot gets the whole panel, and nothing wheel-zooms on hover (Alan: squishy
and tight, angular plot small and useless, weird per-plot scroll)."""

from PySide6.QtCore import Qt


def _plot_keys(selector):
    keys = []
    for i in range(selector.count()):
        key = selector.item(i).data(Qt.ItemDataRole.UserRole)
        if key:
            keys.append(key)
    return keys


def test_browser_shows_placeholder_with_no_data(qtbot):
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard

    d = StatsDashboard()
    qtbot.addWidget(d)
    assert d._host.currentWidget() is d._placeholder
    assert _plot_keys(d._selector) == [], "nothing to plot before any data"


def test_browser_offers_many_plots_and_focuses_one(
    qtbot, variant_graph_result, sample_ebsd
):
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard

    d = StatsDashboard()
    qtbot.addWidget(d)
    d.set_context(result=variant_graph_result, ebsd_map=sample_ebsd, or_type="KS")

    keys = _plot_keys(d._selector)
    assert len(keys) >= 6, "the browser offers many plots, not four squished ones"
    # one plot is focused (the host shows a built plot, not the placeholder)
    assert d._current_key in keys
    assert d._host.currentWidget() is not d._placeholder


def test_selecting_a_plot_focuses_it_lazily(
    qtbot, variant_graph_result, sample_ebsd
):
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard

    d = StatsDashboard()
    qtbot.addWidget(d)
    d.set_context(result=variant_graph_result, ebsd_map=sample_ebsd, or_type="KS")

    d._select_key("pole_figure")  # the "angular plot" now gets the whole panel
    assert d._current_key == "pole_figure"
    assert "pole_figure" in d._built, "selected plot is built + cached lazily"


def test_summary_dock_exists(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert "Summary" in w._docks
    assert w._docks["Summary"] in w._bottom_docks
