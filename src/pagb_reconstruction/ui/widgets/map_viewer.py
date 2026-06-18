import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsOpacityEffect,
    QLabel,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from orix.vector import Vector3d

from pagb_reconstruction.utils.colormap import DEFAULT_IPF_DIRECTION, ipf_key_image
from pagb_reconstruction.utils.math_ops import MisorientationOps

from pagb_reconstruction.core.base import _MapPropertyMeta
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.theme import (
    ACCENT,
    DARK_FG,
    GRID_COLOR,
    SURFACE_DIM,
    TEXT_DISABLED,
    TEXT_MUTED,
    active_theme,
)
from pagb_reconstruction.ui.widgets.compute_worker import ComputeWorker

logger = logging.getLogger(__name__)

_INSTANT_MODES = frozenset({"Phase", "Band Contrast", "Grain ID", "Euler Angles"})
_IPF_DIRECTIONS = {
    "IPF-X": Vector3d.xvector(),
    "IPF-Y": Vector3d.yvector(),
    "IPF-Z": Vector3d.zvector(),
}


class MapViewer(QWidget):
    pixel_hovered = Signal(int, int)
    pixel_clicked = Signal(int, int)
    roi_changed = Signal(int, int, int, int)

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
        self._line_mode = False
        self._line_start: tuple[int, int] | None = None
        self._line_item: pg.PlotDataItem | None = None
        self._split_mode = False
        self._roi_active = False
        self._roi_item: pg.RectROI | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._display_combo = QComboBox()
        self._display_combo.setMinimumWidth(100)
        self._display_combo.currentTextChanged.connect(self._update_display)

        self._hist_eq_cb = QCheckBox("Equalize")
        self._hist_eq_cb.toggled.connect(self._on_hist_eq_toggled)

        self._graphics_view = pg.GraphicsLayoutWidget()
        self._plot = self._graphics_view.addPlot()
        self._plot.setAspectLocked(True, ratio=1)
        self._plot.invertY(True)
        self._plot.getViewBox().setDefaultPadding(0)
        self._plot.hideButtons()
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

        self._highlight_item = pg.ImageItem()
        self._highlight_item.setZValue(11)
        self._plot.addItem(self._highlight_item)
        self._highlight_item.setVisible(False)

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
        self._colorbar_plot.setMaximumWidth(84)
        self._colorbar_plot.setMouseEnabled(x=False, y=False)
        self._colorbar_label_min = pg.TextItem("", anchor=(0.5, 0))
        self._colorbar_label_max = pg.TextItem("", anchor=(0.5, 1))
        self._colorbar_plot.addItem(self._colorbar_label_min)
        self._colorbar_plot.addItem(self._colorbar_label_max)
        self._colorbar_plot.setVisible(False)

        # IPF colour-key triangle, shown beside the map for orientation maps
        # (an IPF map is uninterpretable without its key).
        self._ipf_key_item = pg.ImageItem(axisOrder="row-major")
        self._ipf_key_plot = self._graphics_view.addPlot()
        self._ipf_key_plot.addItem(self._ipf_key_item)
        self._ipf_key_plot.hideAxis("left")
        self._ipf_key_plot.hideAxis("bottom")
        self._ipf_key_plot.setAspectLocked(True)
        self._ipf_key_plot.invertY(True)
        self._ipf_key_plot.setMouseEnabled(x=False, y=False)
        self._ipf_key_plot.setMaximumWidth(150)
        self._ipf_key_plot.setVisible(False)

        self._split_plot = self._graphics_view.addPlot()
        self._split_plot.setAspectLocked(True)
        self._split_plot.invertY(True)
        self._split_image_item = pg.ImageItem()
        self._split_plot.addItem(self._split_image_item)
        self._split_plot.hideAxis("left")
        self._split_plot.hideAxis("bottom")
        self._split_plot.setVisible(False)

        self._split_combo = QComboBox()
        self._split_combo.currentTextChanged.connect(self._update_split_display)

        self._scalebar_item = pg.ScaleBar(size=10, suffix="µm")
        self._scalebar_item.setParentItem(self._plot.vb)
        self._scalebar_item.anchor((1, 1), (1, 1), offset=(-20, -20))
        self._scalebar_item.hide()

        self._proxy = pg.SignalProxy(
            self._plot.scene().sigMouseMoved, rateLimit=30, slot=self._on_mouse_move
        )

        layout.addWidget(self._graphics_view, 1)

        self._computing_overlay = QLabel("", self._graphics_view)
        self._computing_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._computing_overlay.setStyleSheet(
            f"background: rgba(0, 0, 0, 180); color: {ACCENT}; font-size: 14px; "
            "font-weight: bold; padding: 12px 24px; border-radius: 8px;"
        )
        self._computing_overlay.setVisible(False)

        self._overlay_opacity = QGraphicsOpacityEffect(self._computing_overlay)
        self._computing_overlay.setGraphicsEffect(self._overlay_opacity)
        self._overlay_anim = QPropertyAnimation(self._overlay_opacity, b"opacity")
        self._overlay_anim.setDuration(800)
        self._overlay_anim.setStartValue(0.6)
        self._overlay_anim.setEndValue(1.0)
        self._overlay_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._overlay_anim.setLoopCount(-1)

        self._status_strip = QLabel("")
        self._status_strip.setFixedHeight(20)
        self._status_strip.setStyleSheet(
            f"background: {SURFACE_DIM}; color: {TEXT_MUTED}; padding: 2px 4px; "
            f"font-size: 11px; font-family: monospace; border-top: 1px solid {GRID_COLOR};"
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()

    def _position_overlay(self):
        if self._computing_overlay.isVisible():
            self._computing_overlay.adjustSize()
            gw = self._graphics_view.width()
            gh = self._graphics_view.height()
            ow = self._computing_overlay.width()
            oh = self._computing_overlay.height()
            self._computing_overlay.move((gw - ow) // 2, (gh - oh) // 2)

    def _on_hist_eq_toggled(self, checked: bool):
        self._hist_eq_enabled = checked
        self._update_display()

    def _populate_combo(self):
        self._display_combo.blockSignals(True)
        self._display_combo.clear()
        self._split_combo.blockSignals(True)
        self._split_combo.clear()
        metas = [
            m
            for m in EBSDMap.registered_map_properties()
            if not (m.requires_result and self._result is None)
        ]
        # Group the long flat list by category, separators between groups.
        categories = []
        for m in metas:
            if m.category not in categories:
                categories.append(m.category)
        for ci, cat in enumerate(categories):
            if ci > 0:
                self._display_combo.insertSeparator(self._display_combo.count())
            for m in metas:
                if m.category == cat:
                    self._display_combo.addItem(m.name)
                    self._split_combo.addItem(m.name)
        self._display_combo.blockSignals(False)
        self._split_combo.blockSignals(False)

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
        # Show the result automatically — the user should not have to hunt the
        # parent map in the list after a long compute.
        idx = self._display_combo.findText("Parent + Boundaries")
        if idx >= 0:
            self._display_combo.setCurrentIndex(idx)
        else:
            self._update_display()

    def clear(self):
        self._ebsd_map = None
        self._result = None
        self._current_image = None
        self._image_item.clear()
        self._boundary_item.clear()
        self.clear_highlight()
        self._colorbar_plot.setVisible(False)
        self._ipf_key_plot.setVisible(False)
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

        if mode in _INSTANT_MODES:
            image = self._compute_image(mode)
            self._on_compute_done(image, meta, gen)
            return

        self._computing_overlay.setText(f"Computing {mode}...")
        self._computing_overlay.setVisible(True)
        self._position_overlay()
        self._overlay_anim.start()
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
        self._overlay_anim.stop()
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
            if display.dtype == np.float32 or display.dtype == np.float64:
                display = (np.clip(display, 0, 1) * 255).astype(np.uint8)
            self._image_item.setImage(display, autoLevels=False, levels=(0, 255))
            self._image_item.setLookupTable(None)
            self._colorbar_plot.setVisible(False)
            self._update_ipf_key(meta)
        else:
            display = self._apply_hist_eq(image) if self._hist_eq_enabled else image
            self._ipf_key_plot.setVisible(False)
            if meta and meta.dtype == "discrete":
                # Distinct colour per id — a continuous ramp made Packet/Block/
                # Variant nearly one colour. (Per-id swatch legend still TODO.)
                self._image_item.setImage(display, autoLevels=False, levels=(0, 255))
                self._image_item.setLookupTable(self._categorical_lut())
                self._colorbar_plot.setVisible(False)
            else:
                cmap_name = (
                    meta.colormap if meta and meta.colormap else self._colormap_name
                )
                cmap = pg.colormap.get(cmap_name, source="matplotlib")
                lut = cmap.getLookupTable(nPts=256)
                self._image_item.setImage(display, autoLevels=True)
                self._image_item.setLookupTable(lut)
                self._update_colorbar(display, meta)
        self._update_boundary()
        self._update_scalebar()
        self._plot.getViewBox().autoRange(padding=0)

    @staticmethod
    def _categorical_lut() -> np.ndarray:
        base = pg.colormap.get("tab20", source="matplotlib").getLookupTable(
            nPts=20, alpha=False
        )
        return np.array([base[i % len(base)] for i in range(256)], dtype=np.ubyte)

    def _update_ipf_key(self, meta: _MapPropertyMeta | None):
        name = meta.name if meta else ""
        if "IPF" not in name or self._ebsd_map is None:
            self._ipf_key_plot.setVisible(False)
            return
        direction = _IPF_DIRECTIONS.get(name, DEFAULT_IPF_DIRECTION)
        try:
            img = ipf_key_image(self._ebsd_map.primary_symmetry(), direction)
        except Exception:
            self._ipf_key_plot.setVisible(False)
            return
        self._ipf_key_item.setImage(img, autoLevels=False, levels=(0, 255))
        h, w = img.shape[:2]
        self._ipf_key_item.setRect(0, 0, w, h)
        self._ipf_key_plot.setVisible(True)
        self._ipf_key_plot.getViewBox().autoRange(padding=0.02)

    def _on_compute_error(self, msg, generation):
        if generation != self._compute_generation:
            return
        self._computing_overlay.setText(f"Error: {msg}")
        self._overlay_anim.stop()
        self._overlay_opacity.setOpacity(1.0)
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

    def _update_colorbar(self, image: np.ndarray, meta: _MapPropertyMeta | None = None):
        finite = image[np.isfinite(image)]
        if finite.size == 0:
            self._colorbar_plot.setVisible(False)
            return
        vmin, vmax = float(finite.min()), float(finite.max())
        if vmax <= vmin:
            vmax = vmin + 1.0
        # Match the map's colormap so the bar and map agree.
        cmap_name = meta.colormap if meta and meta.colormap else self._colormap_name
        cmap = pg.colormap.get(cmap_name, source="matplotlib")
        lut = cmap.getLookupTable(nPts=256)
        gradient = np.linspace(0, 1, 256).reshape(256, 1)
        self._colorbar_item.setImage(gradient, autoLevels=False, levels=(0, 1))
        self._colorbar_item.setLookupTable(lut)
        # Place the bar over the REAL data range so the left axis reads in data
        # units (not the 0-256 LUT row index).
        self._colorbar_item.setRect(0, vmin, 1, vmax - vmin)
        self._colorbar_label_min.setText("")
        self._colorbar_label_max.setText("")
        # Units on the vertical axis label (won't clip like a narrow title).
        self._colorbar_plot.setLabel(
            "left", meta.name if meta else "value", units=meta.unit if meta else None
        )
        self._colorbar_plot.showAxis("left")
        self._colorbar_plot.setVisible(True)
        self._colorbar_plot.setYRange(vmin, vmax)
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
        self._scalebar_item.text.setText(f"{bar_size} µm")
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

            flat = self._ebsd_map.pixel_index_at(y, x)
            if flat < 0:
                self._status_strip.setText(f"  ({x}, {y})  |  not indexed")
                self.pixel_hovered.emit(x, y)
                return
            euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
            phi1, Phi, phi2 = euler[flat]
            pid = int(self._ebsd_map.phase_ids[flat])
            pname = self._ebsd_map.phase_name(pid)
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

        if self._line_mode:
            self._handle_line_click(x, y)
            return

        flat_idx = y * cols + x
        euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
        phi1, Phi, phi2 = euler[flat_idx]
        phase_id = int(self._ebsd_map.phase_ids[flat_idx])
        phase_name = "?"
        for p in self._ebsd_map.phases:
            if p.phase_id == phase_id:
                phase_name = p.name
                break

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

    def toggle_line_mode(self):
        self._line_mode = not self._line_mode
        if not self._line_mode:
            self._clear_line()
            self._line_start = None

    def _clear_line(self):
        if self._line_item is not None:
            self._plot.removeItem(self._line_item)
            self._line_item = None

    def _handle_line_click(self, x: int, y: int):
        if self._line_start is None:
            self._line_start = (x, y)
            self._clear_line()
            self._line_item = self._plot.plot(
                [x + 0.5],
                [y + 0.5],
                pen=pg.mkPen(
                    active_theme().warning, width=2, style=Qt.PenStyle.DashLine
                ),
                symbol="o",
                symbolSize=6,
            )
        else:
            x0, y0 = self._line_start
            self._line_item.setData([x0 + 0.5, x + 0.5], [y0 + 0.5, y + 0.5])
            self._show_misorientation_profile(x0, y0, x, y)
            self._line_start = None
            self._line_mode = False

    def _show_misorientation_profile(self, x0: int, y0: int, x1: int, y1: int):
        if self._ebsd_map is None:
            return

        rows, cols = self._ebsd_map.shape
        n_points = max(abs(x1 - x0), abs(y1 - y0)) + 1
        xs = np.linspace(x0, x1, n_points).astype(int)
        ys = np.linspace(y0, y1, n_points).astype(int)

        quats = self._ebsd_map.quaternions
        sym_quats = self._ebsd_map._primary_symmetry_quats()
        step = self._ebsd_map.step_size[1]

        angles = np.zeros(n_points - 1)
        for i in range(n_points - 1):
            idx_a = ys[i] * cols + xs[i]
            idx_b = ys[i + 1] * cols + xs[i + 1]
            if 0 <= idx_a < len(quats) and 0 <= idx_b < len(quats):
                angles[i] = MisorientationOps.pair(
                    quats[idx_a], quats[idx_b], sym_quats
                )

        distances = (
            np.arange(n_points - 1)
            * step
            * np.sqrt(
                ((x1 - x0) / max(n_points - 1, 1)) ** 2
                + ((y1 - y0) / max(n_points - 1, 1)) ** 2
            )
        )

        p = active_theme()
        dialog = QDialog(self)
        dialog.setWindowTitle("Misorientation Profile")
        dialog.resize(500, 300)
        layout = QVBoxLayout(dialog)
        plot_widget = pg.PlotWidget()
        plot_widget.setBackground(p.surface_dim)
        plot_widget.setTitle("Misorientation along line", size="10pt")
        plot_widget.setLabel("bottom", "Distance", units="µm")
        plot_widget.setLabel("left", "Misorientation", units="\u00b0")
        plot_widget.showGrid(x=True, y=True, alpha=0.2)
        plot_widget.plot(distances, angles, pen=pg.mkPen(p.accent, width=2))
        layout.addWidget(plot_widget)
        dialog.show()

    def toggle_split_mode(self):
        self._split_mode = not self._split_mode
        self._split_plot.setVisible(self._split_mode)
        if self._split_mode:
            self._split_plot.setXLink(self._plot)
            self._split_plot.setYLink(self._plot)
            self._split_combo.setVisible(True)
            self._update_split_display()
        else:
            self._split_plot.setXLink(None)
            self._split_plot.setYLink(None)
            self._split_combo.setVisible(False)

    def set_split_visible(self, visible: bool):
        self._split_mode = visible
        self._split_plot.setVisible(visible)
        self._split_combo.setVisible(visible)
        if visible:
            self._split_plot.setXLink(self._plot)
            self._split_plot.setYLink(self._plot)
            self._update_split_display()
        else:
            self._split_plot.setXLink(None)
            self._split_plot.setYLink(None)

    def _update_split_display(self):
        if not self._split_mode or self._ebsd_map is None:
            return
        mode = self._split_combo.currentText()
        if not mode:
            return
        try:
            image = self._ebsd_map.compute_map_property(mode)
        except KeyError:
            return
        meta = self._find_meta(mode)
        is_rgb = (
            meta.dtype == "rgb"
            if meta
            else (image.ndim == 3 and image.shape[2] in (3, 4))
        )
        if is_rgb:
            self._split_image_item.setImage(image, autoLevels=True)
            self._split_image_item.setLookupTable(None)
        else:
            cmap_name = meta.colormap if meta and meta.colormap else self._colormap_name
            cmap = pg.colormap.get(cmap_name, source="matplotlib")
            lut = cmap.getLookupTable(nPts=256)
            self._split_image_item.setImage(image, autoLevels=True)
            self._split_image_item.setLookupTable(lut)

    def toggle_roi_mode(self):
        self._roi_active = not self._roi_active
        if self._roi_active:
            if self._roi_item is None:
                rows, cols = (100, 100)
                if self._ebsd_map:
                    rows, cols = self._ebsd_map.shape
                w, h = cols // 4, rows // 4
                x, y = cols // 4, rows // 4
                self._roi_item = pg.RectROI(
                    [x, y], [w, h], pen=pg.mkPen(ACCENT, width=2)
                )
                self._roi_item.sigRegionChanged.connect(self._on_roi_changed)
                self._plot.addItem(self._roi_item)
            else:
                self._roi_item.setVisible(True)
        else:
            if self._roi_item is not None:
                self._roi_item.setVisible(False)

    def clear_roi(self):
        if self._roi_item is not None:
            self._plot.removeItem(self._roi_item)
            self._roi_item = None
        self._roi_active = False

    def get_roi_bounds(self) -> tuple[int, int, int, int] | None:
        if self._roi_item is None:
            return None
        pos = self._roi_item.pos()
        size = self._roi_item.size()
        return (int(pos.x()), int(pos.y()), int(size.x()), int(size.y()))

    def _on_roi_changed(self):
        bounds = self.get_roi_bounds()
        if bounds:
            self.roi_changed.emit(*bounds)

    def highlight_parent(self, parent_grain_id: int) -> None:
        if self._ebsd_map is None or self._result is None:
            return
        if parent_grain_id < 0:
            self.clear_highlight()
            return
        parent_ids = self._ebsd_map._to_grid(self._result.parent_grain_ids, fill=-1)
        mask = parent_ids == parent_grain_id
        if not np.any(mask):
            self.clear_highlight()
            return
        rgba = np.zeros((*mask.shape, 4), dtype=np.float32)
        rgba[mask, 0] = 1.0
        rgba[mask, 1] = 0.9
        rgba[mask, 2] = 0.2
        rgba[mask, 3] = 0.35
        self._highlight_item.setImage(rgba, autoLevels=False, levels=(0, 1))
        self._highlight_item.setVisible(True)

    def clear_highlight(self) -> None:
        self._highlight_item.clear()
        self._highlight_item.setVisible(False)
