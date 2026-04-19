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
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
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
        layout.addWidget(self._detail_label)
        self._list.currentRowChanged.connect(self._show_detail)

    def set_phases(self, phases: list[PhaseConfig]):
        self._phases = list(phases)
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for phase in self._phases:
            item = QListWidgetItem(f"{phase.name} ({phase.point_group})")
            self._list.addItem(item)

    def _show_detail(self, row: int):
        if row < 0 or row >= len(self._phases):
            self._detail_label.setText("")
            return
        phase = self._phases[row]
        info = phase.to_dict_display()
        lines = [f"{k}: {v}" for k, v in info.items()]
        self._detail_label.setText("\n".join(lines))

    def _add_phase(self):
        self._phases.append(PhaseConfig.ferrite())
        self._refresh_list()

    def _remove_phase(self):
        row = self._list.currentRow()
        if row >= 0:
            self._phases.pop(row)
            self._refresh_list()
