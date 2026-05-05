import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.theme import active_theme


class StatCard(QWidget):
    def __init__(self, label: str, value: str = "-"):
        super().__init__()
        self.setFixedSize(80, 60)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size: 9px;")
        layout.addWidget(self._label)

        self._value = QLabel(value)
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._value)

        self._apply_style()

    def _apply_style(self):
        p = active_theme()
        self.setStyleSheet(
            f"StatCard {{ background: {p.surface}; border-radius: 6px; }}"
        )
        self._label.setStyleSheet(f"font-size: 9px; color: {p.text_muted};")
        self._value.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {p.accent};"
        )

    def set_value(self, text: str):
        self._value.setText(text)


class ChartWidget(QWidget):
    def __init__(self, title: str):
        super().__init__()
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setTitle(title, size="9pt")
        self._plot_widget.setMinimumSize(200, 150)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self._plot_widget.setMouseEnabled(x=False, y=False)
        layout.addWidget(self._plot_widget)

        self._plot_widget.scene().sigMouseClicked.connect(self._on_click)
        self._apply_style()

    def _apply_style(self):
        p = active_theme()
        self._plot_widget.setBackground(p.surface_dim)
        self._plot_widget.getAxis("bottom").setPen(pg.mkPen(p.border))
        self._plot_widget.getAxis("left").setPen(pg.mkPen(p.border))
        self._plot_widget.getAxis("bottom").setTextPen(pg.mkPen(p.text_muted))
        self._plot_widget.getAxis("left").setTextPen(pg.mkPen(p.text_muted))

    def plot(self) -> pg.PlotItem:
        return self._plot_widget.getPlotItem()

    def clear(self):
        self._plot_widget.clear()

    def _on_click(self, event):
        if event.double():
            self._show_expanded()

    def _show_expanded(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self._title)
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        expanded = pg.PlotWidget()
        expanded.setTitle(self._title)
        expanded.showGrid(x=True, y=True, alpha=0.2)
        p = active_theme()
        expanded.setBackground(p.surface_dim)

        source_plot = self._plot_widget.getPlotItem()
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
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        self._card_parents = StatCard("Parents")
        self._card_fit = StatCard("Mean Fit")
        self._card_recon = StatCard("% Recon")
        self._card_time = StatCard("Time")
        cards_row.addWidget(self._card_parents)
        cards_row.addWidget(self._card_fit)
        cards_row.addWidget(self._card_recon)
        cards_row.addWidget(self._card_time)
        cards_row.addStretch()
        layout.addLayout(cards_row)

        self._chart_grid = QGridLayout()
        self._chart_grid.setSpacing(4)

        self._chart_grain_size = ChartWidget("Grain Size")
        self._chart_misori = ChartWidget("Misorientation")
        self._chart_variants = ChartWidget("Variants")
        self._chart_fit = ChartWidget("Fit Angles")

        self._chart_grid.addWidget(self._chart_grain_size, 0, 0)
        self._chart_grid.addWidget(self._chart_misori, 0, 1)
        self._chart_grid.addWidget(self._chart_variants, 1, 0)
        self._chart_grid.addWidget(self._chart_fit, 1, 1)
        layout.addLayout(self._chart_grid, 1)

    def update_stats(
        self,
        result: ReconstructionResult,
        ebsd_map: EBSDMap | None = None,
        elapsed: float = 0.0,
    ):
        p = active_theme()
        parent_ids = result.parent_grain_ids
        unique_parents = np.unique(parent_ids[parent_ids >= 0])
        n_parents = len(unique_parents)

        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        mean_fit = float(np.mean(fit_valid)) if len(fit_valid) > 0 else 0.0
        pct_recon = float(np.sum(parent_ids >= 0) / max(len(parent_ids), 1) * 100)

        self._card_parents.set_value(str(n_parents))
        self._card_fit.set_value(f"{mean_fit:.2f}\u00b0")
        self._card_recon.set_value(f"{pct_recon:.1f}%")
        self._card_time.set_value(f"{elapsed:.1f}s" if elapsed > 0 else "-")

        sizes = np.array([int(np.sum(parent_ids == pid)) for pid in unique_parents])
        self._plot_grain_size(sizes, p)
        self._plot_misorientation(fit_valid, p)
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
