import logging
import time
import warnings

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QFont, QPainter
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

# Every array we draw is numpy (row, col); pyqtgraph's default is col-major, which
# TRANSPOSES it — a landscape map rendered as a narrow portrait strip, and the
# hover/click hit-testing (which indexes [row][col]) reading the wrong pixel.
# Set process-wide here, before any ImageItem is constructed, so the map, overlays,
# colour bar and IPF key are all consistent.
pg.setConfigOption("imageAxisOrder", "row-major")
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.theme import active_theme
from pagb_reconstruction.ui.widgets.compute_worker import ComputeWorker

logger = logging.getLogger(__name__)

_INSTANT_MODES = frozenset({"Phase", "Band Contrast", "Grain ID", "Euler Angles"})
_IPF_DIRECTIONS = {
    "IPF-X": Vector3d.xvector(),
    "IPF-Y": Vector3d.yvector(),
    "IPF-Z": Vector3d.zvector(),
}


def _nice_bar_length(width_um: float) -> float:
    """A round scale-bar length (1, 2 or 5 x a power of ten) about 1/5 of the
    map width — a bar reading "3.7 µm" is unusable. Mirrors the figure export's
    nice_scale_length so the live bar and the exported one agree."""
    if width_um <= 0:
        return 1.0
    target = width_um / 5.0
    base = 10.0 ** np.floor(np.log10(target))
    for multiple in (5.0, 2.0, 1.0):
        if multiple * base <= target:
            return float(multiple * base)
    return float(base)


class _ScaleBar(pg.ScaleBar):
    """Scale bar anchored BOTTOM-LEFT.

    pyqtgraph's stock bar grows LEFTWARD (rect ``[-w, 0]``) and centres its label
    at ``-w/2``, so anchored bottom-left both fall off the left edge and only the
    unit survives — the number is clipped (found live, 2026-07-22). This grows
    RIGHTWARD instead, and carries a bold white label on a dark chip so it reads
    over a bright IPF map, like the reference OIM exports.
    """

    def __init__(self, size, suffix="µm"):
        super().__init__(size=size, width=6, suffix=suffix)
        self.text.setParentItem(None)  # drop the stock label, rebuild it bolder
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.text = pg.TextItem(
            text="", color=(255, 255, 255), anchor=(0.5, 1),
            fill=pg.mkBrush(0, 0, 0, 150),
        )
        self.text.setFont(font)
        self.text.setParentItem(self)

    def updateBar(self):
        view = self.parentItem()
        if view is None:
            return
        p1 = view.mapFromViewToItem(self, QPointF(0, 0))
        p2 = view.mapFromViewToItem(self, QPointF(self.size, 0))
        w = (p2 - p1).x()
        self.bar.setRect(QRectF(0, 0, w, self._width))
        self.text.setPos(w / 2.0, 0)


class MapViewer(QWidget):
    line_mode_changed = Signal(bool)
    parent_boundary_changed = Signal(bool)
    pixel_hovered = Signal(int, int)
    pixel_clicked = Signal(int, int)
    roi_changed = Signal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._colormap_name = "viridis"
        self._boundary_visible = False
        self._parent_boundary_visible = False
        self._antialias_enabled = True
        self._fps_visible = False
        self._fps_last_t: float | None = None
        self._fps_smooth: float | None = None
        self._current_image: np.ndarray | None = None
        self._hist_eq_enabled = False
        self._active_worker: ComputeWorker | None = None
        # Workers superseded by a newer request. A running QThread must stay
        # referenced until it really stops, or Qt aborts the process.
        self._retired_workers: set[ComputeWorker] = set()
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
        # Smooth pixmap transform stops the map from aliasing into a cross-hatch
        # moiré on fractional-scaling displays (Windows 125/150 %), where the
        # default nearest-neighbour draw at a non-integer scale drops rows/cols
        # in a regular pattern. Reported as "très pixelisé".
        self._graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._plot = self._graphics_view.addPlot()
        self._plot.setAspectLocked(True, ratio=1)
        self._plot.invertY(True)
        self._plot.getViewBox().setDefaultPadding(0)
        self._plot.hideButtons()
        self._image_item = pg.ImageItem()
        self._image_item.setAutoDownsample(True)
        self._plot.addItem(self._image_item)
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")

        self._image_item.mouseClickEvent = self._on_image_click

        self._boundary_item = pg.ImageItem()
        self._boundary_item.setZValue(10)
        self._boundary_item.setOpacity(0.5)
        self._plot.addItem(self._boundary_item)
        self._boundary_item.setVisible(False)

        # Reconstructed parent (prior-austenite) boundaries: thin BLACK vector
        # lines over the orientation map — the signature PAGB view. 1 px cosmetic
        # so they stay crisp at any zoom (a rasterised mask would thin to nothing
        # zoomed out) yet don't swamp a full map that has hundreds of parents.
        # Above the yellow child boundaries.
        _parent_pen = pg.mkPen(color=(0, 0, 0), width=1)
        _parent_pen.setCosmetic(True)
        self._parent_boundary_item = pg.PlotCurveItem(pen=_parent_pen)
        self._parent_boundary_item.setZValue(10.5)
        self._plot.addItem(self._parent_boundary_item)
        self._parent_boundary_item.setVisible(False)

        self._highlight_item = pg.ImageItem()
        self._highlight_item.setZValue(11)
        self._plot.addItem(self._highlight_item)
        self._highlight_item.setVisible(False)

        self._crosshair_h = pg.InfiniteLine(
            angle=0, pen=pg.mkPen(active_theme().accent, width=1, style=Qt.PenStyle.DashLine)
        )
        self._crosshair_v = pg.InfiniteLine(
            angle=90, pen=pg.mkPen(active_theme().accent, width=1, style=Qt.PenStyle.DashLine)
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
        self._colorbar_plot.setVisible(False)

        # IPF colour-key triangle, shown beside the map for orientation maps
        # (an IPF map is uninterpretable without its key).
        self._ipf_key_item = pg.ImageItem()
        self._ipf_key_plot = self._graphics_view.addPlot()
        self._ipf_key_plot.addItem(self._ipf_key_item)
        self._ipf_key_plot.hideAxis("left")
        self._ipf_key_plot.hideAxis("bottom")
        self._ipf_key_plot.setAspectLocked(True)
        self._ipf_key_plot.invertY(True)
        self._ipf_key_plot.setMouseEnabled(x=False, y=False)
        self._ipf_key_plot.setMaximumWidth(110)
        self._ipf_key_plot.setVisible(False)

        self._split_plot = self._graphics_view.addPlot()
        self._split_plot.setAspectLocked(True)
        self._split_plot.invertY(True)
        self._split_image_item = pg.ImageItem()
        self._split_image_item.setAutoDownsample(True)
        self._split_plot.addItem(self._split_image_item)
        self._split_plot.hideAxis("left")
        self._split_plot.hideAxis("bottom")
        self._split_plot.setVisible(False)

        self._split_combo = QComboBox()
        self._split_combo.currentTextChanged.connect(self._update_split_display)

        # Bottom-LEFT, matching the reference OIM exports Eloïse works from.
        self._scalebar_item = _ScaleBar(size=10, suffix="µm")
        self._scalebar_item.setParentItem(self._plot.vb)
        self._scalebar_item.anchor((0, 1), (0, 1), offset=(20, -20))
        self._scalebar_item.hide()

        self._proxy = pg.SignalProxy(
            self._plot.scene().sigMouseMoved, rateLimit=30, slot=self._on_mouse_move
        )

        layout.addWidget(self._graphics_view, 1)

        # Key for categorical maps (Packet/Block/Variant/Phase). Hidden when the
        # map has too many categories for a legend to mean anything.
        self._legend_label = QLabel("", self)
        self._legend_label.setObjectName("categoryLegend")
        self._legend_label.setTextFormat(Qt.TextFormat.RichText)
        self._legend_label.setVisible(False)
        layout.addWidget(self._legend_label)

        # Armed-mode hint: without it, arming line-profile mode is invisible
        # and the toolbar button reads as dead (audited live).
        self._hint_label = QLabel("", self._graphics_view)
        self._hint_label.setObjectName("modeHint")
        self._hint_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setVisible(False)

        # Sample reference frame (which way X/Y run on the map), like the axis
        # cross on the OIM exports. y is drawn top-to-bottom (invertY), so Y
        # points DOWN. Sits quietly in the top-left of the map.
        self._axis_indicator = QLabel(
            "X&nbsp;→<br>Y&nbsp;↓", self._graphics_view
        )
        self._axis_indicator.setObjectName("axisIndicator")
        self._axis_indicator.setTextFormat(Qt.TextFormat.RichText)
        self._axis_indicator.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._axis_indicator.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._axis_indicator.move(10, 8)
        self._axis_indicator.setVisible(False)

        # Optional FPS counter (top-right). Measures the map view's real repaint
        # rate, so a blocked event loop (e.g. a slow hover handler) reads as low
        # fps. Off by default; toggled from the View toolbar. It watches the
        # viewport's paint events via an event filter.
        self._fps_label = QLabel("", self._graphics_view)
        self._fps_label.setObjectName("fpsCounter")
        self._fps_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._fps_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._fps_label.setVisible(False)
        self._graphics_view.viewport().installEventFilter(self)

        self._computing_overlay = QLabel("", self._graphics_view)
        self._computing_overlay.setObjectName("computingOverlay")
        # Without this a QLabel parented to a QGraphicsView ignores its
        # stylesheet background, leaving the text unreadable over the map.
        self._computing_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._computing_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._computing_overlay.setVisible(False)

        self._overlay_opacity = QGraphicsOpacityEffect(self._computing_overlay)
        self._computing_overlay.setGraphicsEffect(self._overlay_opacity)
        # A looping opacity pulse multiplied the scrim's own alpha (0.94 rendered
        # as ~0.65 measured), dropping text contrast under the readable floor.
        # Fade in once and stay solid; readability beats the breathing effect.
        self._overlay_opacity.setOpacity(1.0)
        self._overlay_anim = QPropertyAnimation(self._overlay_opacity, b"opacity")
        self._overlay_anim.setDuration(180)
        self._overlay_anim.setStartValue(0.0)
        self._overlay_anim.setEndValue(1.0)
        self._overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._overlay_anim.setLoopCount(1)

        self._status_strip = QLabel("")
        self._status_strip.setFixedHeight(20)
        self._status_strip.setObjectName("statusStrip")
        layout.addWidget(self._status_strip)

        self._grain_overlay = QLabel("")
        self._grain_overlay.setWordWrap(True)
        self._grain_overlay.setObjectName("grainOverlay")
        self._grain_overlay.setVisible(False)
        layout.addWidget(self._grain_overlay)

        self._placeholder = QLabel(
            "Drop an EBSD file here or use Ctrl+O to open\n\n"
            "Supported formats: .ang, .ctf, .h5, .hdf5"
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("mapPlaceholder")
        layout.addWidget(self._placeholder)
        self._graphics_view.setVisible(False)
        self._status_strip.setVisible(False)

        self._plot.vb.setMenuEnabled(False)
        self._plot.vb.scene().sigMouseClicked.connect(self._on_right_click)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.Paint
            and obj is self._graphics_view.viewport()
            and self._fps_visible
        ):
            now = time.perf_counter()
            if self._fps_last_t is not None:
                dt = now - self._fps_last_t
                if dt > 0:
                    inst = 1.0 / dt
                    self._fps_smooth = (
                        inst
                        if self._fps_smooth is None
                        else 0.85 * self._fps_smooth + 0.15 * inst
                    )
                    self._fps_label.setText(f"{self._fps_smooth:.0f} fps")
                    self._fps_label.adjustSize()
                    self._fps_label.move(
                        max(0, self._graphics_view.width() - self._fps_label.width() - 8),
                        8,
                    )
            self._fps_last_t = now
        return super().eventFilter(obj, event)

    def set_fps_visible(self, visible: bool):
        """Show/hide the FPS counter. Repaint timing only accrues while shown."""
        self._fps_visible = bool(visible)
        self._fps_smooth = None
        self._fps_last_t = None
        if visible:
            self._fps_label.setText("— fps")
            self._fps_label.adjustSize()
            self._fps_label.move(
                max(0, self._graphics_view.width() - self._fps_label.width() - 8), 8
            )
        self._fps_label.setVisible(visible)
        self._fps_label.raise_()

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
        self._axis_indicator.setVisible(True)
        self._axis_indicator.raise_()
        self._populate_combo()
        self._update_scalebar()
        self._update_display()

    def set_reconstruction_result(self, result: ReconstructionResult):
        self._result = result
        if self._ebsd_map:
            self._ebsd_map.set_result(result)
        self._populate_combo()
        # Land on the reference PAGB view: the measured orientations (IPF-Z)
        # with the reconstructed parent boundaries drawn on top — exactly the
        # overlay Eloïse compares against. The user should not have to assemble
        # it by hand after a long compute.
        self._parent_boundary_visible = True
        self.parent_boundary_changed.emit(True)
        idx = self._display_combo.findText("IPF-Z")
        if idx >= 0:
            self._display_combo.setCurrentIndex(idx)
        else:
            self._update_display()
        # The base map recomputes async; draw the boundaries now (they need only
        # the result), and _on_compute_done redraws them over the finished map.
        self._update_parent_boundary()

    def clear(self):
        self._ebsd_map = None
        self._result = None
        self._current_image = None
        self._image_item.clear()
        self._boundary_item.clear()
        self._parent_boundary_item.setVisible(False)
        self.clear_highlight()
        self._colorbar_plot.setVisible(False)
        self._ipf_key_plot.setVisible(False)
        self._axis_indicator.setVisible(False)
        self._scalebar_item.hide()
        self._graphics_view.setVisible(False)
        self._status_strip.setVisible(False)
        self._crosshair_h.setVisible(False)
        self._crosshair_v.setVisible(False)
        self._placeholder.setVisible(True)

    def current_image(self):
        """The data currently displayed (not the rendered pixmap)."""
        return self._current_image

    def current_parent_segments(self):
        """Parent-boundary segments IF the overlay is currently shown, else
        None — so an exported figure carries the same lines the user sees."""
        if not self._parent_boundary_visible or self._ebsd_map is None:
            return None
        try:
            return self._ebsd_map.parent_boundary_segments()
        except Exception:
            return None

    def current_meta(self):
        """Metadata for the current display mode (unit, colormap, dtype)."""
        return self._find_meta(self._display_combo.currentText())

    def current_display_mode(self) -> str:
        return self._display_combo.currentText()

    def set_colormap(self, name: str):
        self._colormap_name = name
        self._update_display()

    def set_boundary_overlay(self, visible: bool):
        self._boundary_visible = visible
        self._update_boundary()

    def set_parent_boundary_overlay(self, visible: bool):
        self._parent_boundary_visible = bool(visible)
        self._update_parent_boundary()

    def set_antialiasing(self, enabled: bool):
        """Smooth the map image, or show it as crisp nearest-neighbour pixels.

        OFF renders the real EBSD grid pixel-for-pixel — for inspecting the data
        at its true resolution. ON smooths it AND suppresses the fractional-scale
        moiré ("très pixelisé") on Windows 125/150 % displays, so it is the
        default. Vector overlays (boundaries, scale bar) keep their own
        anti-aliasing regardless — only the raster image is affected."""
        self._antialias_enabled = bool(enabled)
        self._graphics_view.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, enabled
        )
        self._image_item.setAutoDownsample(enabled)
        self._split_image_item.setAutoDownsample(enabled)
        self._graphics_view.viewport().update()

    def select_display_index(self, index: int):
        if index < self._display_combo.count():
            self._display_combo.setCurrentIndex(index)

    def zoom(self, factor: float):
        self._plot.vb.scaleBy((1 / factor, 1 / factor))

    def zoom_fit(self):
        self._plot.autoRange()

    def export_image(self, path: str):
        """Raw plot export. Interactive decorations (click crosshair, ROI,
        grain highlight, measure line) are session state, not data — issue #13:
        "on a le cadre noir autour et le curseur de sélection quand on
        enregistre". Hide them for the render, restore after."""
        decorations = [
            self._crosshair_h,
            self._crosshair_v,
            self._highlight_item,
            self._roi_item,
            self._line_item,
        ]
        shown = [d for d in decorations if d is not None and d.isVisible()]
        for d in shown:
            d.setVisible(False)
        try:
            exporter = pg.exporters.ImageExporter(self._plot)
            exporter.export(path)
        finally:
            for d in shown:
                d.setVisible(True)

    def _update_display(self):
        if self._ebsd_map is None:
            return
        mode = self._display_combo.currentText()
        if not mode:
            return

        self._compute_generation += 1
        gen = self._compute_generation

        self._retire_active_worker()

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
        worker.result.connect(
            lambda img, g=gen, m=meta: self._on_compute_done(img, m, g)
        )
        worker.error.connect(lambda msg, g=gen: self._on_compute_error(msg, g))
        self._active_worker = worker
        worker.start()

    def _retire_active_worker(self):
        """Detach the in-flight worker but keep it alive until it stops.

        Its result is ignored via the generation counter; dropping the reference
        while the thread runs would destroy a running QThread and abort the app.
        """
        worker = self._active_worker
        self._active_worker = None
        if worker is None:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for signal in (worker.result, worker.error):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
        if worker.isRunning():
            self._retired_workers.add(worker)
            worker.finished.connect(
                lambda w=worker: self._retired_workers.discard(w)
            )

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
        # Equalisation is a CONTRAST STRETCH, so it only means anything on a
        # continuous scalar field (Band Contrast, KAM, GOS, Fit Angle). On the
        # other two kinds the colour IS the data and stretching corrupts it: a
        # discrete map's values are id LABELS, so remapping them scrambles the
        # palette (a 2-phase map rendered as banded rainbow noise), and an RGB
        # map's channels encode orientation, so per-channel stretching reports a
        # different orientation than measured. Disable rather than silently
        # ignore — an enabled control that does nothing is a false affordance.
        equalisable = not is_rgb and not (meta and meta.dtype == "discrete")
        self._hist_eq_cb.setEnabled(equalisable)
        apply_eq = self._hist_eq_enabled and equalisable

        if is_rgb:
            self._legend_label.setVisible(False)
            display = image
            if display.dtype == np.float32 or display.dtype == np.float64:
                display = (np.clip(display, 0, 1) * 255).astype(np.uint8)
            self._image_item.setImage(display, autoLevels=False, levels=(0, 255))
            self._image_item.setLookupTable(None)
            self._colorbar_plot.setVisible(False)
            self._update_ipf_key(meta)
        else:
            display = self._apply_hist_eq(image) if apply_eq else image
            self._ipf_key_plot.setVisible(False)
            if meta and meta.dtype == "discrete":
                # Distinct colour per id — a continuous ramp made Packet/Block/
                # Variant nearly one colour. Ids CYCLE through the palette rather
                # than clamping: with thousands of ids (parent grains) everything
                # past the last entry used to render in a single colour.
                lut = self._categorical_lut()
                self._image_item.setImage(
                    self._discrete_indices(display, len(lut)),
                    autoLevels=False,
                    levels=(0, len(lut) - 1),
                )
                self._image_item.setLookupTable(lut)
                self._colorbar_plot.setVisible(False)
                self._update_category_legend(display, meta.name if meta else "")
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
        self._update_parent_boundary()
        self._update_scalebar()
        self._plot.getViewBox().autoRange(padding=0)


    _MAX_LEGEND_CATEGORIES = 24

    def _update_category_legend(self, image, mode: str):
        """Show a swatch key for a categorical map, or hide it when useless."""
        data = np.asarray(image)
        finite = data[np.isfinite(data)]
        cats = np.unique(finite[finite >= 0]).astype(int) if finite.size else np.array([])
        if cats.size == 0 or cats.size > self._MAX_LEGEND_CATEGORIES:
            self._legend_label.setVisible(False)
            return

        lut = self._categorical_lut()
        chips = []
        for cat in cats:
            idx = int(self._discrete_indices(np.array([[float(cat)]]), len(lut))[0, 0])
            r, g, b = (int(v) for v in lut[idx])
            chips.append(
                f'<span style="background-color:rgb({r},{g},{b});">&nbsp;&nbsp;&nbsp;</span>'
                f'&nbsp;<span>{cat}</span>'
            )
        self._legend_label.setText(
            f'<b>{mode}</b>&nbsp;&nbsp;' + "&nbsp;&nbsp;&nbsp;".join(chips)
        )
        self._legend_label.setVisible(True)

    @staticmethod
    def _discrete_indices(image, n_colors: int) -> np.ndarray:
        """Map ids onto LUT slots 1..n-1, reserving slot 0 for "no id".

        Modulo, never clamp: a map with more ids than LUT entries would otherwise
        draw every id past the last entry in one flat colour.
        """
        ids = np.asarray(image)
        valid = np.isfinite(ids) & (ids >= 0)
        idx = np.zeros(ids.shape, dtype=np.float32)
        idx[valid] = (ids[valid].astype(np.int64) % (n_colors - 1)) + 1
        return idx

    @staticmethod
    def _categorical_lut() -> np.ndarray:
        """Slot 0 = neutral "no id" grey; 1..255 cycle the tab20 palette."""
        base = pg.colormap.get("tab20", source="matplotlib").getLookupTable(
            nPts=20, alpha=False
        )
        lut = np.empty((256, 3), dtype=np.ubyte)
        lut[0] = (46, 46, 46)
        for i in range(1, 256):
            lut[i] = base[(i - 1) % len(base)]
        return lut

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
        axis = name.split("-")[1] if "-" in name else "Z"
        # Name the phase(s) the key colours, like the "Austenite" / "Ferrite"
        # labels on the OIM triangles. Both cubic phases share one triangle, so
        # one correctly-labelled key serves both rather than cloning two.
        phases = ", ".join(p.name for p in self._ebsd_map.phases)
        title = f"IPF ∥ {axis}"
        if phases:
            title += f"<br><span style='font-size:7pt'>{phases}</span>"
        self._ipf_key_plot.setTitle(title, size="8pt")
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
        # Drop the previous map: leaving it up would present another map's data
        # as if it were the one the user selected.
        self._current_image = None
        self._image_item.clear()
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
        # grain_boundary_map() is float (it passes through _to_grid, which needs
        # a float fill); indexing with it directly raised IndexError inside this
        # slot on every draw, so the overlay silently never appeared.
        boundary = np.asarray(self._ebsd_map.grain_boundary_map())
        mask = np.isfinite(boundary) & (boundary > 0)
        rgba = np.zeros((*boundary.shape, 4), dtype=np.float32)
        rgba[mask, 0] = 1.0
        rgba[mask, 1] = 1.0
        rgba[mask, 3] = 0.6
        self._boundary_item.setImage(rgba, autoLevels=False, levels=(0, 1))
        self._boundary_item.setVisible(True)

    def _update_parent_boundary(self):
        if not self._parent_boundary_visible or self._ebsd_map is None:
            self._parent_boundary_item.setVisible(False)
            return
        try:
            segments = self._ebsd_map.parent_boundary_segments()
        except Exception:
            segments = None
        if segments is None or len(segments[0]) == 0:
            # No reconstruction (or an empty one) — nothing to outline.
            self._parent_boundary_item.setVisible(False)
            return
        xs, ys = segments
        self._parent_boundary_item.setData(xs, ys, connect="pairs")
        self._parent_boundary_item.setVisible(True)

    def _update_scalebar(self):
        if self._ebsd_map is None:
            self._scalebar_item.hide()
            return
        step = self._ebsd_map.step_size[1]
        cols = self._ebsd_map.shape[1]
        width_um = step * cols
        bar_um = _nice_bar_length(width_um)
        bar_px = bar_um / step if step > 0 else 10
        self._scalebar_item.size = bar_px
        self._scalebar_item.text.setText(f"{bar_um:g} µm")
        # Setting .size alone does not redraw; the stock bar only refreshes on a
        # view range change. Redraw now so the new length shows immediately.
        self._scalebar_item.updateBar()
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
            # One pixel, not the whole map: converting all orientations to Euler
            # here cost ~170 ms per mouse-move (the hover lag).
            phi1, Phi, phi2 = self._ebsd_map.pixel_euler(flat)
            pid = int(self._ebsd_map.phase_ids[flat])
            pname = self._ebsd_map.phase_name(pid)
            iq = self._ebsd_map.band_contrast_map()[y, x]
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

    def toggle_line_mode(self, enabled: bool | None = None):
        # Slot for QAction.toggled(bool); the old zero-argument form raised
        # TypeError on every click, leaving the toolbar button silently dead.
        self._line_mode = (not self._line_mode) if enabled is None else bool(enabled)
        if self._line_mode:
            # An armed mode must LOOK armed: crosshair + a one-line next step,
            # or the button reads as doing nothing.
            self._graphics_view.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._show_hint("Line profile: click two points on the map")
        else:
            self._disarm_line_mode()

    def _disarm_line_mode(self, keep_line: bool = False) -> None:
        """Single place that takes the mode out of its armed appearance.

        Re-entrant by construction: telling the toolbar we disarmed unchecks its
        action, whose toggled(False) calls back into here. Without the guard the
        second pass ran with keep_line defaulting to False and erased the line
        the user had just measured — invisible to a MapViewer-only test, since
        nothing is connected to the signal there.
        """
        if getattr(self, "_disarming", False):
            return
        self._disarming = True
        try:
            self._disarm_line_mode_inner(keep_line)
        finally:
            self._disarming = False

    def _disarm_line_mode_inner(self, keep_line: bool) -> None:
        was_armed = self._line_mode
        self._line_mode = False
        self._graphics_view.viewport().unsetCursor()
        self._hint_label.setVisible(False)
        if not keep_line:
            self._clear_line()
        self._line_start = None
        if was_armed:
            # Tell the toolbar, or its button stays visually pressed.
            self.line_mode_changed.emit(False)

    def _show_hint(self, text: str) -> None:
        self._hint_label.setText(text)
        self._hint_label.adjustSize()
        self._hint_label.move(
            max(0, (self._graphics_view.width() - self._hint_label.width()) // 2), 8
        )
        self._hint_label.setVisible(True)
        self._hint_label.raise_()

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
            # Above the map and every overlay (boundary 10, highlight 11). Left
            # at the default 0 it painted UNDER the image and was invisible,
            # while the profile dialog still showed correct data — which made it
            # look like a coordinate bug rather than a paint-order one.
            self._line_item.setZValue(12)
        else:
            x0, y0 = self._line_start
            self._line_item.setData([x0 + 0.5, x + 0.5], [y0 + 0.5, y + 0.5])
            self._line_start = None
            # Disarm BEFORE opening the profile dialog. Disarming afterwards left
            # the crosshair, banner and pressed toolbar button on screen for as
            # long as the dialog was up, claiming the tool was still armed. Keep
            # the drawn line: _clear_line() would erase the profile just measured.
            self._disarm_line_mode(keep_line=True)
            self._show_misorientation_profile(x0, y0, x, y)

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
                    [x, y], [w, h], pen=pg.mkPen(active_theme().accent, width=2)
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
        self._zoom_to_mask(mask)

    def _zoom_to_mask(self, mask: np.ndarray) -> None:
        """Move the view to the highlighted region — "locate it", as the panel says.

        A worst-fit parent is usually among the SMALLEST grains (that is why it
        fits badly), so tinting it in place on a full-map view leaves it
        invisible. Framed with context around it so the grain is still readable
        against its neighbours rather than filling the canvas.
        """
        rows_idx, cols_idx = np.nonzero(mask)
        if rows_idx.size == 0:
            return
        y0, y1 = int(rows_idx.min()), int(rows_idx.max())
        x0, x1 = int(cols_idx.min()), int(cols_idx.max())

        # Keep a margin of at least the grain's own size, and never zoom past a
        # readable floor — a 3px grain filling the canvas is as useless as one
        # lost in the map.
        span = max(x1 - x0, y1 - y0, 1)
        margin = max(span, 25)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        half = span / 2 + margin
        self._plot.getViewBox().setRange(
            xRange=(cx - half, cx + half),
            yRange=(cy - half, cy + half),
            padding=0,
        )

    def clear_highlight(self) -> None:
        self._highlight_item.clear()
        self._highlight_item.setVisible(False)
