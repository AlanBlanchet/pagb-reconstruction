"""Pole figure — the Child/Parent selector must switch the plotted orientation
source. It was wired to replot the same single array, so Mode did nothing."""

import numpy as np


def test_mode_selector_switches_child_vs_parent_source(qtbot):
    from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget

    w = PoleFigureWidget()
    qtbot.addWidget(w)
    child = np.tile([1.0, 0.0, 0.0, 0.0], (5, 1))
    parent = np.tile([0.0, 1.0, 0.0, 0.0], (5, 1))
    w.set_orientations(child=child, parent=parent)

    w._mode_combo.setCurrentText("Child")
    assert w._orientations is child
    w._mode_combo.setCurrentText("Parent")
    assert w._orientations is parent


def test_pole_figure_handles_missing_orientations(qtbot):
    from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget

    w = PoleFigureWidget()
    qtbot.addWidget(w)
    w.set_orientations(child=None, parent=None)  # must not raise
    assert w._orientations is None
