import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult


class MapViewer(QWidget):
    pixel_hovered = Signal(int, int)
    pixel_clicked = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Display:"))
        self._display_combo = QComboBox()
        self._display_combo.currentTextChanged.connect(self._update_display)
        controls.addWidget(self._display_combo)
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

        layout.addWidget(self._graphics_view)

        self._grain_overlay = QLabel("")
        self._grain_overlay.setWordWrap(True)
        self._grain_overlay.setStyleSheet(
            "background: rgba(0,0,0,180); color: #eee; padding: 6px; font-size: 12px;"
        )
        self._grain_overlay.setVisible(False)
        layout.addWidget(self._grain_overlay)

        self._placeholder = QLabel("Open an EBSD file to display the map")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("font-size: 16px; color: #888;")
        layout.addWidget(self._placeholder)
        self._graphics_view.setVisible(False)

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
        self._populate_combo()
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
        self._image_item.clear()
        self._boundary_item.clear()
        self._graphics_view.setVisible(False)
        self._placeholder.setVisible(True)

    def _update_display(self):
        if self._ebsd_map is None:
            return
        mode = self._display_combo.currentText()
        if not mode:
            return
        image = self._compute_image(mode)
        if image is not None:
            self._image_item.setImage(image, autoLevels=True)

    def _compute_image(self, mode: str) -> np.ndarray | None:
        if self._ebsd_map is None:
            return None
        try:
            return self._ebsd_map.compute_map_property(mode)
        except KeyError:
            return np.zeros(self._ebsd_map.shape)

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
        phase_name = self._ebsd_map.phases[phase_id].name if phase_id < len(self._ebsd_map.phases) else "?"

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
