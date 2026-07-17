"""StyledPlot: themed pyqtgraph plot with copy/export/edit built in."""

import numpy as np


def test_styled_plot_constructs_and_plots(qtbot):
    from pagb_reconstruction.ui.plotting import StyledPlot

    p = StyledPlot("Grain Size", x_label="Size (px)", y_label="Count")
    qtbot.addWidget(p)
    p.plot_bars(np.arange(5.0), np.array([1.0, 4, 2, 5, 3]))
    assert p.plot_item.listDataItems() or p.plot_item.items


def test_styled_plot_export_png_and_csv(qtbot, tmp_path):
    from pagb_reconstruction.ui.plotting import StyledPlot

    p = StyledPlot("t", x_label="x", y_label="y")
    qtbot.addWidget(p)
    p.plot_line(np.arange(10.0), np.arange(10.0) ** 2)
    png = tmp_path / "out.png"
    csv = tmp_path / "out.csv"
    p.export_image(png)
    p.export_csv(csv)
    assert png.stat().st_size > 0
    assert b"x" in csv.read_bytes() or csv.stat().st_size > 0


def test_styled_plot_copy_to_clipboard(qtbot, qapp):
    from pagb_reconstruction.ui.plotting import StyledPlot

    p = StyledPlot("t")
    qtbot.addWidget(p)
    p.plot_line(np.arange(5.0), np.arange(5.0))
    p.copy_to_clipboard()
    assert not qapp.clipboard().image().isNull()


def test_styled_plot_set_labels(qtbot):
    from pagb_reconstruction.ui.plotting import StyledPlot

    p = StyledPlot("old")
    qtbot.addWidget(p)
    p.set_labels(title="new", x_label="X2", y_label="Y2")
    assert p.title == "new"
