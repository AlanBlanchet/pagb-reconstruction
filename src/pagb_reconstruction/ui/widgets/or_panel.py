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
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        preset_group = QGroupBox("Orientation Relationship")
        preset_layout = QFormLayout(preset_group)

        self._or_combo = QComboBox()
        self._or_combo.addItems(OrientationRelationship.preset_names())
        self._or_combo.currentTextChanged.connect(self._update_detail)
        preset_layout.addRow("Preset:", self._or_combo)

        self._optimize_cb = QCheckBox("Optimize OR to data")
        self._optimize_cb.setChecked(True)
        preset_layout.addRow(self._optimize_cb)

        layout.addWidget(preset_group)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)
        layout.addStretch()

        self._update_detail()

    def _update_detail(self):
        name = self._or_combo.currentText()
        if not name:
            return
        or_obj = OrientationRelationship.from_preset(name)
        self._detail_label.setText(or_obj.description)

    def get_or_type(self) -> str:
        return self._or_combo.currentText()

    def get_optimize(self) -> bool:
        return self._optimize_cb.isChecked()
