import numpy as np
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.phase import PhaseConfig


class PhasePanel(QWidget):
    def __init__(self):
        super().__init__()
        self._phases: list[PhaseConfig] = []
        self._phase_pixel_counts: dict[int, int] = {}
        self._total_pixels = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._add_btn.clicked.connect(self._add_phase)
        btn_layout.addWidget(self._add_btn)

        self._remove_btn = QPushButton("Remove")
        self._remove_btn.clicked.connect(self._remove_phase)
        btn_layout.addWidget(self._remove_btn)
        layout.addLayout(btn_layout)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)
        self._list.currentRowChanged.connect(self._show_detail)

    def set_phases(
        self, phases: list[PhaseConfig], phase_ids: np.ndarray | None = None
    ):
        self._phases = list(phases)
        if phase_ids is not None:
            self._total_pixels = len(phase_ids)
            unique, counts = np.unique(phase_ids, return_counts=True)
            self._phase_pixel_counts = dict(zip(unique.tolist(), counts.tolist()))
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for idx, phase in enumerate(self._phases):
            pix_count = self._phase_pixel_counts.get(phase.phase_id, 0)
            vol_frac = (
                pix_count / self._total_pixels * 100 if self._total_pixels > 0 else 0
            )

            swatch = QPixmap(14, 14)
            swatch.fill(QColor(phase.color))

            text = f"  {phase.name} ({phase.point_group})"
            if vol_frac > 0:
                text += f"  —  {vol_frac:.1f}%"
            item = QListWidgetItem(text)
            item.setIcon(swatch)
            self._list.addItem(item)

    def _show_detail(self, row: int):
        if row < 0 or row >= len(self._phases):
            self._detail_label.setText("")
            return
        phase = self._phases[row]
        info = phase.to_dict_display()
        lines = [f"Crystal family: {phase.family.value}"]
        lines.extend(f"{k}: {v}" for k, v in info.items())
        pix_count = self._phase_pixel_counts.get(phase.phase_id, 0)
        if self._total_pixels > 0:
            lines.append(
                f"Volume fraction: {pix_count / self._total_pixels * 100:.1f}% ({pix_count} px)"
            )
        self._detail_label.setText("\n".join(lines))

    def _add_phase(self):
        self._phases.append(PhaseConfig.ferrite())
        self._refresh_list()

    def _remove_phase(self):
        row = self._list.currentRow()
        if row >= 0:
            self._phases.pop(row)
            self._refresh_list()
