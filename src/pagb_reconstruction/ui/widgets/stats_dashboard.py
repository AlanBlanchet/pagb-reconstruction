import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.plotting import StyledPlot
from pagb_reconstruction.ui.theme import active_theme


class StatCard(QWidget):
    def __init__(self, label: str, value: str = "-"):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(64)
        self.setMinimumWidth(110)
        self.setMaximumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setObjectName("statLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._value = QLabel(value)
        self._value.setObjectName("statValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

    def set_value(self, text: str):
        self._value.setText(text)


class ChartWidget(StyledPlot):
    """A dashboard chart: a StyledPlot (copy/export/edit built in) that also
    expands into a dialog on double-click."""

    def __init__(self, title: str, x_label: str = "", y_label: str = ""):
        super().__init__(title, x_label=x_label, y_label=y_label)
        # Fits the bottom dock's shape: full-window WIDE but short. Kept at 120
        # rather than 170 because these docks are TABIFIED — the whole bottom
        # group's minimum height is the TALLEST tab's, so Statistics' floor was
        # clamping the "Map" split preset to ~350px even when Log was showing.
        # A live pass confirmed the charts stay legible down to ~90px plot boxes.
        self._widget.setMinimumSize(200, 120)
        self._widget.scene().sigMouseClicked.connect(self._on_click)

    def plot(self) -> pg.PlotItem:
        return self.plot_item

    def _on_click(self, event):
        if event.double():
            self._show_expanded()

    def _show_expanded(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.title)
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        expanded = pg.PlotWidget()
        expanded.setTitle(self.title)
        expanded.showGrid(x=True, y=True, alpha=0.2)
        p = active_theme()
        expanded.setBackground(p.surface_dim)

        source_plot = self.plot_item
        for item in source_plot.listDataItems():
            if hasattr(item, "getData"):
                x, y = item.getData()
                if x is not None and y is not None:
                    expanded.plot(x, y, pen=item.opts.get("pen"))
            elif hasattr(item, "opts") and "x" in item.opts:
                expanded.addItem(
                    pg.BarGraphItem(
                        x=item.opts["x"],
                        height=item.opts["height"],
                        width=item.opts.get("width", 0.8),
                        brush=item.opts.get("brush"),
                    )
                )
        layout.addWidget(expanded)
        dialog.exec()


class StatsDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        self._chart_grid = QGridLayout()
        self._chart_grid.setSpacing(4)

        self._chart_grain_size = ChartWidget("Grain Size", "Size (px)", "Count")
        self._chart_misori = ChartWidget("Misorientation", "Angle (\u00b0)", "Count")
        self._chart_variants = ChartWidget("Variants", "Variant ID", "Pixels")
        self._chart_fit = ChartWidget("Fit Angles", "Fit (\u00b0)", "Count")

        # One row, not 2x2: the bottom dock has width to spare and no height to
        # spare. Nothing else shares this panel, so the row cannot be starved.
        for col, chart in enumerate(
            (
                self._chart_grain_size,
                self._chart_misori,
                self._chart_variants,
                self._chart_fit,
            )
        ):
            self._chart_grid.addWidget(chart, 0, col)
        outer.addLayout(self._chart_grid, 1)

    def update_stats(
        self,
        result: ReconstructionResult,
        ebsd_map: EBSDMap | None = None,
        elapsed: float = 0.0,
    ):
        self._result = result
        self._ebsd_map = ebsd_map

        p = active_theme()
        parent_ids = result.parent_grain_ids
        unique_parents = np.unique(parent_ids[parent_ids >= 0])
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]

        sizes = np.array([int(np.sum(parent_ids == pid)) for pid in unique_parents])
        self._plot_grain_size(sizes, p)
        misori = ebsd_map.misorientation_angles() if ebsd_map else fit_valid
        self._plot_misorientation(misori, p)
        self._plot_variants(result, p)
        self._plot_fit_angles(fit_valid, p)

    def _plot_grain_size(self, sizes: np.ndarray, p):
        self._chart_grain_size.clear()
        if len(sizes) == 0:
            return
        hist, bin_edges = np.histogram(sizes, bins=min(30, len(sizes)))
        x = (bin_edges[:-1] + bin_edges[1:]) / 2
        width = (bin_edges[1] - bin_edges[0]) * 0.8
        bar = pg.BarGraphItem(x=x, height=hist, width=width, brush=p.accent)
        self._chart_grain_size.plot().addItem(bar)

    def _plot_misorientation(self, fit_valid: np.ndarray, p):
        self._chart_misori.clear()
        if len(fit_valid) == 0:
            return
        hist, bin_edges = np.histogram(fit_valid, bins=50)
        x = (bin_edges[:-1] + bin_edges[1:]) / 2
        self._chart_misori.plot().plot(x, hist, pen=pg.mkPen(p.warning, width=2))

    def _plot_variants(self, result: ReconstructionResult, p):
        self._chart_variants.clear()
        variant_ids = result.variant_ids
        valid = variant_ids[variant_ids >= 0]
        if len(valid) == 0:
            return
        unique_v, counts = np.unique(valid, return_counts=True)
        bar = pg.BarGraphItem(
            x=unique_v.astype(float), height=counts, width=0.8, brush=p.info
        )
        self._chart_variants.plot().addItem(bar)

    def _plot_fit_angles(self, fit_valid: np.ndarray, p):
        self._chart_fit.clear()
        if len(fit_valid) == 0:
            return
        hist, bin_edges = np.histogram(fit_valid, bins=40)
        x = (bin_edges[:-1] + bin_edges[1:]) / 2
        width = (bin_edges[1] - bin_edges[0]) * 0.8
        bar = pg.BarGraphItem(x=x, height=hist, width=width, brush=p.success)
        self._chart_fit.plot().addItem(bar)
