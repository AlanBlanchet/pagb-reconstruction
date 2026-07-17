"""StyledPlot — the one reusable plot component.

Every in-app chart goes through this: themed, beautiful defaults (padded axes,
soft grid, antialiased marks) plus built-in right-click actions — Copy image,
Export PNG / SVG / CSV, Edit labels — so plots are publication-ready without
leaving the app.
"""

import csv
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter, SVGExporter
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.ui.theme import active_theme, icon


class StyledPlot(QWidget):
    """Themed pyqtgraph plot with copy / export / label-editing built in."""

    def __init__(
        self,
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.title = title
        self._x_label = x_label
        self._y_label = y_label

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._widget = pg.PlotWidget()
        layout.addWidget(self._widget)

        self.plot_item = self._widget.getPlotItem()
        self._widget.setMouseEnabled(x=False, y=False)
        self.plot_item.vb.setMenuEnabled(False)
        self._widget.setContextMenuPolicy(pg.QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._widget.customContextMenuRequested.connect(self._show_menu)

        self.restyle()

    # ── styling ─────────────────────────────────────────────────────
    def restyle(self) -> None:
        p = active_theme()
        self._widget.setBackground(p.surface_dim)
        self._widget.setAntialiasing(True)
        self.plot_item.showGrid(x=True, y=True, alpha=0.15)
        self.plot_item.setContentsMargins(4, 4, 8, 4)
        for side in ("bottom", "left"):
            ax = self.plot_item.getAxis(side)
            ax.setPen(pg.mkPen(p.border))
            ax.setTextPen(pg.mkPen(p.text_muted))
        self._apply_labels()

    def _apply_labels(self) -> None:
        p = active_theme()
        self.plot_item.setTitle(self.title or None, color=p.fg, size="9pt")
        self.plot_item.setLabel("bottom", self._x_label or None)
        self.plot_item.setLabel("left", self._y_label or None)

    def set_labels(
        self,
        title: str | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
    ) -> None:
        if title is not None:
            self.title = title
        if x_label is not None:
            self._x_label = x_label
        if y_label is not None:
            self._y_label = y_label
        self._apply_labels()

    # ── data ────────────────────────────────────────────────────────
    def clear(self) -> None:
        self.plot_item.clear()

    def plot_line(self, x: np.ndarray, y: np.ndarray, color: str | None = None) -> None:
        pen = pg.mkPen(color or active_theme().accent, width=2)
        self.plot_item.plot(x, y, pen=pen)

    def plot_bars(self, x: np.ndarray, height: np.ndarray,
                  width: float = 0.8, color: str | None = None) -> None:
        c = color or active_theme().accent
        self.plot_item.addItem(
            pg.BarGraphItem(x=x, height=height, width=width,
                            brush=c, pen=pg.mkPen(c))
        )
        if len(height):
            self.plot_item.setYRange(0, float(np.max(height)) * 1.05, padding=0)

    # ── actions ─────────────────────────────────────────────────────
    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setPixmap(self._widget.grab())

    def export_image(self, path: str | Path) -> None:
        path = Path(path)
        if path.suffix.lower() == ".svg":
            SVGExporter(self.plot_item).export(str(path))
        else:
            exporter = ImageExporter(self.plot_item)
            exporter.parameters()["width"] = 1600
            exporter.export(str(path))

    def export_csv(self, path: str | Path) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([self._x_label or "x", self._y_label or "y"])
            for item in self.plot_item.listDataItems():
                x, y = item.getData()
                if x is None:
                    continue
                writer.writerows(zip(x, y))
            for item in self.plot_item.items:
                if isinstance(item, pg.BarGraphItem):
                    writer.writerows(zip(item.opts["x"], item.opts["height"]))

    # ── context menu ────────────────────────────────────────────────
    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        for text, ic, fn in (
            ("Copy image", "export_image", self.copy_to_clipboard),
            ("Export…", "export_data", self._export_dialog),
            ("Edit labels…", "params", self._edit_dialog),
        ):
            act = QAction(icon(ic), text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        menu.exec(self._widget.mapToGlobal(pos))

    def _export_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export plot", f"{self.title or 'plot'}.png",
            "PNG image (*.png);;SVG vector (*.svg);;CSV data (*.csv)",
        )
        if not path:
            return
        if path.lower().endswith(".csv"):
            self.export_csv(path)
        else:
            self.export_image(path)

    def _edit_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit labels")
        form = QFormLayout(dlg)
        t = QLineEdit(self.title)
        x = QLineEdit(self._x_label)
        y = QLineEdit(self._y_label)
        form.addRow("Title:", t)
        form.addRow("X axis:", x)
        form.addRow("Y axis:", y)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec():
            self.set_labels(t.text(), x.text(), y.text())
