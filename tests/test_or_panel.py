"""OR panel ergonomics.

The misorientation histogram is the one plot in this panel, and the panel is a
side dock capped at 380 px wide. Two things therefore decide whether it is
readable or a letterbox: it must absorb the panel's spare vertical space rather
than cede it to a trailing stretch, and it must say which mark is the measured
distribution and which are the theoretical OR peaks.
"""

import pyqtgraph as pg


def _panel(qtbot):
    from pagb_reconstruction.ui.widgets.or_panel import ORPanel

    panel = ORPanel()
    qtbot.addWidget(panel)
    return panel


def test_histogram_absorbs_spare_vertical_space(qtbot):
    panel = _panel(qtbot)
    layout = panel._histogram_group.parentWidget().layout()

    index = layout.indexOf(panel._histogram_group)
    assert index != -1, "histogram group must be in the panel layout"
    assert layout.stretch(index) > 0, (
        "the histogram must take the panel's spare height; with stretch 0 a "
        "trailing addStretch() eats it and the plot renders as a letterbox"
    )


def test_histogram_is_tall_enough_to_read(qtbot):
    panel = _panel(qtbot)
    assert panel._hist_plot.minimumHeight() >= 200, (
        "a 90-bin histogram in a 380 px-wide dock needs real height"
    )


def test_histogram_labels_its_marks(qtbot, sample_ebsd):
    panel = _panel(qtbot)
    panel.set_ebsd_map(sample_ebsd)

    legend = panel._hist_plot.plotItem.legend
    assert legend is not None, "histogram must carry a legend"

    labels = {item[1].text for item in legend.items}
    assert any("easured" in text for text in labels), (
        f"the measured distribution must be named; got {labels}"
    )
    assert any("heoretical" in text or "OR" in text for text in labels), (
        f"the dashed theoretical-OR peaks must be named; got {labels}"
    )
