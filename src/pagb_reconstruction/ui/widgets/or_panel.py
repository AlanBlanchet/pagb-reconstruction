import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship


class ORPanel(QWidget):
    or_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
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
        layout.addWidget(self._info_box)

        self._histogram_group = QGroupBox("Misorientation Distribution")
        hist_layout = QVBoxLayout(self._histogram_group)
        self._hist_plot = pg.PlotWidget()
        self._hist_plot.setBackground("#1e1e2e")
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

        if self._ebsd_map_ref is not None:
            _, angles = self._ebsd_map_ref._pair_angles()
            hist, bin_edges = np.histogram(angles, bins=90, range=(0, 90))
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            self._hist_plot.plot(
                bin_centers,
                hist,
                stepMode=False,
                pen=pg.mkPen("#cdd6f4", width=1.5),
                fillLevel=0,
                fillBrush=(205, 214, 244, 40),
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
                    pen=pg.mkPen("#f38ba8", width=1.5, style=2),
                )
                self._hist_plot.addItem(line)
                self._peak_lines.append(line)
