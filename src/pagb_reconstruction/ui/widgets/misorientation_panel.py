"""Misorientation distribution — the measured spectrum against the OR's peaks.

This is the chart that answers "does the selected orientation relationship match
this material?", so it needs to be READ, not glanced at. It lives in the wide
bottom dock rather than the 380px OR sidebar: there it shared one scroll area
with two text-heavy group boxes that consumed the viewport budget first, leaving
~38px and no visible axis at a 900px window. A chart competing with text fields
for height loses; here it owns its vertical budget.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.ui.theme import active_theme


class MisorientationPanel(QWidget):
    """Histogram of measured pair misorientations + the theoretical OR peaks."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._hist_plot = pg.PlotWidget()
        # A diagnostic plot is not a zoomable canvas: the wheel scrolled/zoomed
        # this one (unlike the dashboard charts), the "weird" per-plot scroll
        # Alan reported. Freeze the view + drop the right-drag menu.
        self._hist_plot.setMouseEnabled(x=False, y=False)
        self._hist_plot.getPlotItem().getViewBox().setMenuEnabled(False)
        self._hist_plot.setBackground(active_theme().surface_dim)
        self._hist_plot.setLabel("bottom", "Angle", units="°")
        self._hist_plot.setLabel("left", "Count")
        self._hist_plot.showGrid(x=True, y=True, alpha=0.2)
        # Counts span ~450k at the near-zero spike down to <15k at the OR peaks
        # this plot exists to show; on a linear axis those peaks read as flat.
        self._hist_plot.setLogMode(x=False, y=True)
        self._hist_plot.addLegend(offset=(-10, 10), labelTextColor=active_theme().fg)
        layout.addWidget(self._hist_plot, 1)

        self._peak_lines: list[pg.InfiniteLine] = []
        self._ebsd_map_ref = None
        self._or_type: str = ""

    def set_ebsd_map(self, ebsd_map) -> None:
        self._ebsd_map_ref = ebsd_map
        self._replot()

    def set_or_type(self, or_type: str) -> None:
        self._or_type = or_type
        self._replot()

    def _replot(self) -> None:
        self._hist_plot.clear()
        self._peak_lines.clear()
        legend = self._hist_plot.plotItem.legend
        if legend is not None:
            legend.clear()

        p = active_theme()
        if self._ebsd_map_ref is not None:
            _, angles = self._ebsd_map_ref._pair_angles()
            hist, bin_edges = np.histogram(angles, bins=90, range=(0, 90))
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            self._hist_plot.plot(
                bin_centers,
                hist,
                stepMode=False,
                pen=pg.mkPen(p.accent, width=1.5),
                fillLevel=0,
                fillBrush=p.rgb("accent") + (50,),
                name="Measured misorientations",
            )

        if not self._or_type:
            return
        or_obj = OrientationRelationship.from_preset(self._or_type)
        unique_peaks = np.unique(np.round(or_obj.theoretical_misorientations(), 1))
        peak_pen = pg.mkPen(p.warning, width=1.5, style=Qt.PenStyle.DashLine)
        for angle in unique_peaks:
            line = pg.InfiniteLine(pos=angle, angle=90, pen=peak_pen)
            self._hist_plot.addItem(line)
            self._peak_lines.append(line)
        if legend is not None and self._peak_lines:
            # One entry for the whole dashed family, not one per peak.
            legend.addItem(
                pg.PlotDataItem(pen=peak_pen), f"Theoretical {self._or_type} peaks"
            )
