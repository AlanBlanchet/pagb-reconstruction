"""Statistics panel — charts only.

Three live verdicts drove this shape. The charts began in a 2x2 grid demanding
>=380px of height inside a ~230px dock, so the panel could never show its own
content. Laying them in one row was the wrong lever: the stat cards plus the
Grain Size Measurement group consumed the whole dock budget before the charts
were reached, so a 1x1 grid would have failed identically. Capping that header
at 180px freed the charts but hid the Measure button behind ~800px of content in
a 180px window, with a mouse-wheel dead-zone over its combo and spin boxes.

So the header is not budgeted against the charts at all — it lives in its own
panel, and Statistics holds charts and nothing else.
"""


def test_statistics_holds_charts_and_nothing_else(qtbot):
    from PySide6.QtWidgets import QScrollArea

    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard

    d = StatsDashboard()
    qtbot.addWidget(d)

    assert d.findChild(QScrollArea) is None, (
        "charts-only panel needs no scroll area; one means something is still "
        "competing with the charts for height"
    )
    rows = {d._chart_grid.getItemPosition(i)[0] for i in range(d._chart_grid.count())}
    assert rows == {0}, f"charts share one row to fit a short, wide dock; got {rows}"


def test_summary_dock_exists(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert "Summary" in w._docks
    assert w._docks["Summary"] in w._bottom_docks
