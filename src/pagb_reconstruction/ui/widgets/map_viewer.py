import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.base import _MapPropertyMeta
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.theme import (
    ACCENT,
    DARK_FG,
    EDGE_COLOR,
    GRID_COLOR,
    SURFACE_DIM,
    TEXT_DISABLED,
    TEXT_MUTED,
)
from pagb_reconstruction.ui.widgets.compute_worker import ComputeWorker

logger = logging.getLogger(__name__)


class MapViewer(QWidget):
    pixel_hovered = Signal(int, int)
    pixel_clicked = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._colormap_name = "viridis"
        self._boundary_visible = False
        self._current_image: np.ndarray | None = None
        self._hist_eq_enabled = False
        self._active_worker: ComputeWorker | None = None
        self._compute_generation = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Display:"))
        self._display_combo = QComboBox()
        self._display_combo.currentTextChanged.connect(self._update_display)
        controls.addWidget(self._display_combo)

        self._hist_eq_cb = QCheckBox("Hist. EQ")
        self._hist_eq_cb.toggled.connect(self._on_hist_eq_toggled)
        controls.addWidget(self._hist_eq_cb)

        controls.addStretch()

        self._info_label = QLabel("")
        controls.addWidget(self._info_label)
        layout.addLayout(controls)

        self._graphics_view = pg.GraphicsLayoutWidget()
        self._plot = self._graphics_view.addPlot()
        self._plot.setAspectLocked(True)
        self._plot.invertY(True)
        self._image_item = pg.ImageItem()
        self._plot.addItem(self._image_item)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")

        self._image_item.mouseClickEvent = self._on_image_click

        self._boundary_item = pg.ImageItem()
        self._boundary_item.setZValue(10)
        self._boundary_item.setOpacity(0.5)
        self._plot.addItem(self._boundary_item)
        self._boundary_item.setVisible(False)

        self._crosshair_h = pg.InfiniteLine(
            angle=0, pen=pg.mkPen(ACCENT, width=1, style=Qt.PenStyle.DashLine)
        )
        self._crosshair_v = pg.InfiniteLine(
            angle=90, pen=pg.mkPen(ACCENT, width=1, style=Qt.PenStyle.DashLine)
        )
        self._crosshair_h.setVisible(False)
        self._crosshair_v.setVisible(False)
        self._plot.addItem(self._crosshair_h, ignoreBounds=True)
        self._plot.addItem(self._crosshair_v, ignoreBounds=True)

        self._colorbar_item = pg.ImageItem()
        self._colorbar_plot = self._graphics_view.addPlot()
        self._colorbar_plot.addItem(self._colorbar_item)
        self._colorbar_plot.hideAxis("bottom")
        self._colorbar_plot.setMaximumWidth(60)
        self._colorbar_plot.setMouseEnabled(x=False, y=False)
        self._colorbar_label_min = pg.TextItem("", anchor=(0.5, 0))
        self._colorbar_label_max = pg.TextItem("", anchor=(0.5, 1))
        self._colorbar_plot.addItem(self._colorbar_label_min)
        self._colorbar_plot.addItem(self._colorbar_label_max)
        self._colorbar_plot.setVisible(False)

        self._scalebar_item = pg.ScaleBar(size=10, suffix="um")
        self._scalebar_item.setParentItem(self._plot.vb)
        self._scalebar_item.anchor((1, 1), (1, 1), offset=(-20, -20))
        self._scalebar_item.hide()

        self._proxy = pg.SignalProxy(
            self._plot.scene().sigMouseMoved, rateLimit=30, slot=self._on_mouse_move
        )

        layout.addWidget(self._graphics_view, 1)

        self._computing_overlay = QLabel("")
        self._computing_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._computing_overlay.setFixedHeight(32)
        self._computing_overlay.setStyleSheet(
            f"background: {EDGE_COLOR}; color: {ACCENT}; font-size: 13px; "
            "padding: 6px 16px; border-radius: 4px;"
        )
        self._computing_overlay.setVisible(False)
        layout.addWidget(self._computing_overlay)

        self._status_strip = QLabel("")
        self._status_strip.setFixedHeight(22)
        self._status_strip.setStyleSheet(
            f"background: {SURFACE_DIM}; color: {TEXT_MUTED}; padding: 2px 8px; font-size: 11px; font-family: monospace;"
        )
        layout.addWidget(self._status_strip)

        self._grain_overlay = QLabel("")
        self._grain_overlay.setWordWrap(True)
        self._grain_overlay.setStyleSheet(
            f"background: rgba(24,24,37,210); color: {DARK_FG}; padding: 8px 10px; "
            f"font-size: 12px; border-radius: 6px; border: 1px solid {GRID_COLOR};"
        )
        self._grain_overlay.setVisible(False)
        layout.addWidget(self._grain_overlay)

        self._placeholder = QLabel(
            "Drop an EBSD file here or use Ctrl+O to open\n\n"
            "Supported formats: .ang, .ctf, .h5, .hdf5"
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"font-size: 18px; color: {TEXT_DISABLED}; padding: 40px; "
            f"border: 2px dashed {GRID_COLOR}; border-radius: 12px; margin: 40px;"
        )
        layout.addWidget(self._placeholder)
        self._graphics_view.setVisible(False)
        self._status_strip.setVisible(False)

        self._plot.vb.setMenuEnabled(False)
        self._plot.vb.scene().sigMouseClicked.connect(self._on_right_click)

    def _on_hist_eq_toggled(self, checked: bool):
        self._hist_eq_enabled = checked
        self._update_display()

    def _populate_combo(self):
        self._display_combo.blockSignals(True)
        self._display_combo.clear()
        for meta in EBSDMap.registered_map_properties():
            if meta.requires_result and self._result is None:
                continue
            self._display_combo.addItem(meta.name)
        self._display_combo.blockSignals(False)

    def set_ebsd_map(self, ebsd_map: EBSDMap):
        self._ebsd_map = ebsd_map
        self._placeholder.setVisible(False)
        self._graphics_view.setVisible(True)
        self._status_strip.setVisible(True)
        self._populate_combo()
        self._update_scalebar()
        self._update_display()

    def set_reconstruction_result(self, result: ReconstructionResult):
        self._result = result
        if self._ebsd_map:
            self._ebsd_map.set_result(result)
        self._populate_combo()
        self._update_display()

    def clear(self):
        self._ebsd_map = None
        self._result = None
        self._current_image = None
        self._image_item.clear()
        self._boundary_item.clear()
        self._colorbar_plot.setVisible(False)
        self._scalebar_item.hide()
        self._graphics_view.setVisible(False)
        self._status_strip.setVisible(False)
        self._crosshair_h.setVisible(False)
        self._crosshair_v.setVisible(False)
        self._placeholder.setVisible(True)

    def current_display_mode(self) -> str:
        return self._display_combo.currentText()

    def set_colormap(self, name: str):
        self._colormap_name = name
        self._update_display()

    def set_boundary_overlay(self, visible: bool):
        self._boundary_visible = visible
        self._update_boundary()

    def select_display_index(self, index: int):
        if index < self._display_combo.count():
            self._display_combo.setCurrentIndex(index)

    def zoom(self, factor: float):
        self._plot.vb.scaleBy((1 / factor, 1 / factor))

    def zoom_fit(self):
        self._plot.autoRange()

    def export_image(self, path: str):
        exporter = pg.exporters.ImageExporter(self._plot)
        exporter.export(path)

    def _update_display(self):
        if self._ebsd_map is None:
            return
        mode = self._display_combo.currentText()
        if not mode:
            return

        self._compute_generation += 1
        gen = self._compute_generation

        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.finished.disconnect()
            self._active_worker.error.disconnect()
            self._active_worker = None

        meta = self._find_meta(mode)
        self._computing_overlay.setText(f"Computing {mode}...")
        self._computing_overlay.setVisible(True)
        self._display_combo.setEnabled(False)

        worker = ComputeWorker(self._compute_image, mode)
        worker.finished.connect(
            lambda img, g=gen, m=meta: self._on_compute_done(img, m, g)
        )
        worker.error.connect(lambda msg, g=gen: self._on_compute_error(msg, g))
        self._active_worker = worker
        worker.start()

    def _on_compute_done(self, image, meta, generation):
        if generation != self._compute_generation:
            return
        self._computing_overlay.setVisible(False)
        self._display_combo.setEnabled(True)
        self._active_worker = None
        if image is None:
            return
        self._current_image = image
        is_rgb = (
            meta.dtype == "rgb"
            if meta
            else (image.ndim == 3 and image.shape[2] in (3, 4))
        )
        if is_rgb:
            display = self._apply_hist_eq_rgb(image) if self._hist_eq_enabled else image
            self._image_item.setImage(display, autoLevels=True)
            self._image_item.setLookupTable(None)
            self._colorbar_plot.setVisible(False)
        else:
            display = self._apply_hist_eq(image) if self._hist_eq_enabled else image
            cmap_name = meta.colormap if meta and meta.colormap else self._colormap_name
            cmap = pg.colormap.get(cmap_name, source="matplotlib")
            lut = cmap.getLookupTable(nPts=256)
            self._image_item.setImage(display, autoLevels=True)
            self._image_item.setLookupTable(lut)
            self._update_colorbar(display)
        self._update_boundary()

    def _on_compute_error(self, msg, generation):
        if generation != self._compute_generation:
            return
        self._computing_overlay.setText(f"Error: {msg}")
        self._display_combo.setEnabled(True)
        self._active_worker = None
        logger.error("Map computation failed: %s", msg)

    @staticmethod
    def _find_meta(name: str) -> _MapPropertyMeta | None:
        for meta in EBSDMap.registered_map_properties():
            if meta.name == name:
                return meta
        return None

    def _apply_hist_eq(self, image: np.ndarray) -> np.ndarray:
        valid = image[np.isfinite(image)]
        if len(valid) == 0:
            return image
        flat = image.copy().ravel()
        finite_mask = np.isfinite(flat)
        vals = flat[finite_mask]
        sorted_idx = np.argsort(vals)
        ranks = np.empty_like(sorted_idx, dtype=np.float64)
        ranks[sorted_idx] = np.linspace(0, 1, len(vals))
        flat[finite_mask] = ranks
        return flat.reshape(image.shape)

    def _apply_hist_eq_rgb(self, image: np.ndarray) -> np.ndarray:
        result = image.copy()
        for ch in range(min(image.shape[2], 3)):
            result[:, :, ch] = self._apply_hist_eq(image[:, :, ch])
        return result

    def _compute_image(self, mode: str) -> np.ndarray | None:
        if self._ebsd_map is None:
            return None
        try:
            return self._ebsd_map.compute_map_property(mode)
        except KeyError:
            return np.zeros(self._ebsd_map.shape)

    def _update_colorbar(self, image: np.ndarray):
        vmin, vmax = float(np.nanmin(image)), float(np.nanmax(image))
        gradient = np.linspace(0, 1, 256).reshape(256, 1)
        cmap = pg.colormap.get(self._colormap_name, source="matplotlib")
        lut = cmap.getLookupTable(nPts=256)
        self._colorbar_item.setImage(gradient, autoLevels=False, levels=(0, 1))
        self._colorbar_item.setLookupTable(lut)
        self._colorbar_item.setRect(0, 0, 1, 256)
        self._colorbar_label_min.setText(f"{vmin:.2g}")
        self._colorbar_label_min.setPos(0.5, 0)
        self._colorbar_label_max.setText(f"{vmax:.2g}")
        self._colorbar_label_max.setPos(0.5, 256)
        self._colorbar_plot.setVisible(True)
        self._colorbar_plot.setYRange(0, 256)
        self._colorbar_plot.setXRange(0, 1)

    def _update_boundary(self):
        if not self._boundary_visible or self._ebsd_map is None:
            self._boundary_item.setVisible(False)
            return
        boundary = self._ebsd_map.grain_boundary_map()
        rgba = np.zeros((*boundary.shape, 4), dtype=np.float32)
        rgba[boundary, 0] = 1.0
        rgba[boundary, 1] = 1.0
        rgba[boundary, 3] = 0.6
        self._boundary_item.setImage(rgba, autoLevels=False, levels=(0, 1))
        self._boundary_item.setVisible(True)

    def _update_scalebar(self):
        if self._ebsd_map is None:
            self._scalebar_item.hide()
            return
        step = self._ebsd_map.step_size[1]
        cols = self._ebsd_map.shape[1]
        width_um = step * cols
        bar_size = 10 ** int(np.log10(max(width_um / 5, 1)))
        bar_px = bar_size / step if step > 0 else 10
        self._scalebar_item.size = bar_px
        self._scalebar_item.text.setText(f"{bar_size} um")
        self._scalebar_item.show()

    def _on_mouse_move(self, args):
        if self._ebsd_map is None:
            return
        pos = args[0]
        mouse_point = self._plot.vb.mapSceneToView(pos)
        x, y = int(mouse_point.x()), int(mouse_point.y())
        rows, cols = self._ebsd_map.shape
        if 0 <= y < rows and 0 <= x < cols:
            self._crosshair_h.setPos(y + 0.5)
            self._crosshair_v.setPos(x + 0.5)
            self._crosshair_h.setVisible(True)
            self._crosshair_v.setVisible(True)

            flat = y * cols + x
            euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
            phi1, Phi, phi2 = euler[flat]
            pid = int(self._ebsd_map.phase_ids[flat])
            pname = (
                self._ebsd_map.phases[pid].name
                if pid < len(self._ebsd_map.phases)
                else "?"
            )
            bc_map = self._ebsd_map.band_contrast_map()
            iq = bc_map[y, x]
            self._status_strip.setText(
                f"  ({x}, {y})  |  {pname}  |  "
                f"\u03c6\u2081={phi1:.1f}\u00b0 \u03a6={Phi:.1f}\u00b0 \u03c6\u2082={phi2:.1f}\u00b0  |  "
                f"IQ={iq:.0f}"
            )
            self.pixel_hovered.emit(x, y)
        else:
            self._crosshair_h.setVisible(False)
            self._crosshair_v.setVisible(False)
            self._status_strip.setText("")

    def _on_image_click(self, event):
        if self._ebsd_map is None:
            return
        pos = event.pos()
        x, y = int(pos.x()), int(pos.y())
        rows, cols = self._ebsd_map.shape
        if not (0 <= y < rows and 0 <= x < cols):
            self._grain_overlay.setVisible(False)
            return

        flat_idx = y * cols + x
        euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
        phi1, Phi, phi2 = euler[flat_idx]
        phase_id = int(self._ebsd_map.phase_ids[flat_idx])
        phase_name = (
            self._ebsd_map.phases[phase_id].name
            if phase_id < len(self._ebsd_map.phases)
            else "?"
        )

        grain_id = -1
        if self._ebsd_map.grains:
            for g in self._ebsd_map.grains:
                if flat_idx in g.pixel_indices:
                    grain_id = g.id
                    break

        lines = [
            f"Pixel: ({x}, {y})",
            f"Phase: {phase_name} (id={phase_id})",
            f"Euler: ({phi1:.1f}, {Phi:.1f}, {phi2:.1f})",
            f"Grain ID: {grain_id}",
        ]

        if self._result is not None:
            parent_id = int(self._result.parent_grain_ids[flat_idx])
            variant_id = int(self._result.variant_ids[flat_idx])
            fit = float(self._result.fit_angles[flat_idx])
            lines.append(f"Parent ID: {parent_id}")
            lines.append(f"Variant: V{variant_id}")
            lines.append(f"Fit: {fit:.2f}\u00b0")

        self._grain_overlay.setText("\n".join(lines))
        self._grain_overlay.setVisible(True)
        self.pixel_clicked.emit(x, y)

    def _on_right_click(self, event):
        if event.button() != Qt.MouseButton.RightButton:
            return
        menu = QMenu(self)
        if self._current_image is not None:
            copy_action = QAction("Copy Image to Clipboard", self)
            copy_action.triggered.connect(self._copy_to_clipboard)
            menu.addAction(copy_action)
            save_action = QAction("Save Image...", self)
            save_action.triggered.connect(lambda: self._save_current_image())
            menu.addAction(save_action)
        menu.exec(
            event.screenPos().toPoint()
            if hasattr(event, "screenPos")
            else self.cursor().pos()
        )

    def _copy_to_clipboard(self):
        if self._current_image is None:
            return
        exporter = pg.exporters.ImageExporter(self._plot)
        exporter.export(copy=True)

    def _save_current_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", "", "PNG (*.png);;All Files (*)"
        )
        if path:
            self.export_image(path)
