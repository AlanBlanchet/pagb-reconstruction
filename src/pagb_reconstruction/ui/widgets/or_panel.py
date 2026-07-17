import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.ui.theme import active_theme


class ORPanel(QWidget):
    or_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        preset_group = QGroupBox("Orientation Relationship")
        preset_layout = QFormLayout(preset_group)

        self._or_combo = QComboBox()
        self._or_combo.addItems(OrientationRelationship.preset_names())
        self._or_combo.currentTextChanged.connect(self._on_or_changed)
        preset_layout.addRow("Preset:", self._or_combo)

        self._optimize_cb = QCheckBox("Optimize OR to data")
        self._optimize_cb.setChecked(True)
        preset_layout.addRow(self._optimize_cb)

        layout.addWidget(preset_group)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)

        self._info_box = QGroupBox("OR Details")
        info_layout = QFormLayout(self._info_box)
        self._axis_label = QLabel("-")
        self._angle_label = QLabel("-")
        self._miller_parent_label = QLabel("-")
        self._miller_child_label = QLabel("-")
        self._variant_count_label = QLabel("-")
        info_layout.addRow("Rotation axis:", self._axis_label)
        info_layout.addRow("Rotation angle:", self._angle_label)
        info_layout.addRow("Parent plane//dir:", self._miller_parent_label)
        info_layout.addRow("Child plane//dir:", self._miller_child_label)
        info_layout.addRow("Variants:", self._variant_count_label)
        self._refined_label = QLabel("-")
        self._refined_label.setWordWrap(True)
        info_layout.addRow("Refined OR:", self._refined_label)
        layout.addWidget(self._info_box)

        self._histogram_group = QGroupBox("Misorientation Distribution")
        hist_layout = QVBoxLayout(self._histogram_group)
        self._hist_plot = pg.PlotWidget()
        self._hist_plot.setBackground(active_theme().surface_dim)
        self._hist_plot.setLabel("bottom", "Angle", units="\u00b0")
        self._hist_plot.setLabel("left", "Count")
        self._hist_plot.showGrid(x=True, y=True, alpha=0.2)
        self._hist_plot.setMinimumHeight(150)
        hist_layout.addWidget(self._hist_plot)
        layout.addWidget(self._histogram_group)

        self._peak_lines: list[pg.InfiniteLine] = []
        self._ebsd_map_ref = None

        layout.addStretch()
        self._update_detail()

    def _on_or_changed(self, name: str):
        self._update_detail()
        self._update_histogram()
        self.or_changed.emit(name)

    def _update_detail(self):
        name = self._or_combo.currentText()
        if not name:
            return
        if hasattr(self, "_refined_label"):
            self._refined_label.setText("-")
        or_obj = OrientationRelationship.from_preset(name)
        self._detail_label.setText(or_obj.description)

        R = or_obj.rotation_matrix
        angle_rad = np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))
        angle_deg = np.degrees(angle_rad)
        if angle_rad > 1e-6:
            axis = np.array(
                [
                    R[2, 1] - R[1, 2],
                    R[0, 2] - R[2, 0],
                    R[1, 0] - R[0, 1],
                ]
            )
            axis = axis / np.linalg.norm(axis)
            self._axis_label.setText(f"[{axis[0]:.3f}, {axis[1]:.3f}, {axis[2]:.3f}]")
        else:
            self._axis_label.setText("[0, 0, 1]")
        self._angle_label.setText(f"{angle_deg:.2f}\u00b0")

        pp = or_obj.parallel_planes_parent
        dp = or_obj.parallel_dirs_parent
        self._miller_parent_label.setText(
            f"({pp[0]}{pp[1]}{pp[2]}) // [{dp[0]}{dp[1]}{dp[2]}]"
        )
        pc = or_obj.parallel_planes_child
        dc = or_obj.parallel_dirs_child
        self._miller_child_label.setText(
            f"({pc[0]}{pc[1]}{pc[2]}) // [{dc[0]}{dc[1]}{dc[2]}]"
        )

        n_v = or_obj.n_variants
        self._variant_count_label.setText(f"{n_v} variants")

    def get_or_type(self) -> str:
        return self._or_combo.currentText()

    def get_optimize(self) -> bool:
        return self._optimize_cb.isChecked()

    def set_ebsd_map(self, ebsd_map):
        self._ebsd_map_ref = ebsd_map
        self._update_histogram()

    def _update_histogram(self):
        self._hist_plot.clear()
        self._peak_lines.clear()

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
            )

        name = self._or_combo.currentText()
        if name:
            or_obj = OrientationRelationship.from_preset(name)
            peak_angles = or_obj.theoretical_misorientations()
            unique_peaks = np.unique(np.round(peak_angles, 1))
            for angle in unique_peaks:
                line = pg.InfiniteLine(
                    pos=angle,
                    angle=90,
                    pen=pg.mkPen(p.warning, width=1.5, style=Qt.PenStyle.DashLine),
                )
                self._hist_plot.addItem(line)
                self._peak_lines.append(line)

    def set_optimized_or(self, or_instance) -> None:
        if or_instance is None:
            self._refined_label.setText("-")
            return
        R = np.asarray(or_instance.rotation_matrix, dtype=float)
        angle_rad = float(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
        angle_deg = float(np.degrees(angle_rad))
        if angle_rad > 1e-6:
            axis = np.array(
                [R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]
            )
            axis = axis / np.linalg.norm(axis)
        else:
            axis = np.array([0.0, 0.0, 1.0])

        name = self._or_combo.currentText()
        preset_R = (
            OrientationRelationship.from_preset(name).rotation_matrix
            if name
            else np.eye(3)
        )
        preset_angle_rad = float(
            np.arccos(np.clip((np.trace(preset_R) - 1) / 2, -1, 1))
        )
        preset_angle_deg = float(np.degrees(preset_angle_rad))
        if preset_angle_rad > 1e-6:
            paxis = np.array(
                [
                    preset_R[2, 1] - preset_R[1, 2],
                    preset_R[0, 2] - preset_R[2, 0],
                    preset_R[1, 0] - preset_R[0, 1],
                ]
            )
            paxis = paxis / np.linalg.norm(paxis)
        else:
            paxis = np.array([0.0, 0.0, 1.0])

        d_angle = angle_deg - preset_angle_deg
        cos_ax = float(np.clip(abs(np.dot(axis, paxis)), -1.0, 1.0))
        d_axis_deg = float(np.degrees(np.arccos(cos_ax)))
        self._refined_label.setText(
            f"axis [{axis[0]:+.3f}, {axis[1]:+.3f}, {axis[2]:+.3f}], "
            f"θ={angle_deg:.2f}°  "
            f"(Δθ={d_angle:+.2f}°, "
            f"Δaxis={d_axis_deg:.2f}°)"
        )
