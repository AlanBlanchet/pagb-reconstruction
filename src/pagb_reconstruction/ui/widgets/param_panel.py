from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.reconstruction import ReconstructionConfig

_PRESETS = {
    "Default": ReconstructionConfig(),
    "Fine": ReconstructionConfig(
        threshold_deg=1.5,
        tolerance_deg=1.5,
        grain_threshold_deg=3.0,
        min_grain_size=3,
        merge_similar_deg=5.0,
        inflation_power=1.8,
    ),
    "Coarse": ReconstructionConfig(
        threshold_deg=4.0,
        tolerance_deg=4.0,
        grain_threshold_deg=8.0,
        min_grain_size=10,
        merge_similar_deg=10.0,
        inflation_power=1.4,
    ),
}

_FIELD_GROUPS = {
    "Grain Detection": ["grain_threshold_deg", "min_grain_size"],
    "Clustering": [
        "algorithm",
        "or_type",
        "optimize_or",
        "threshold_deg",
        "tolerance_deg",
        "inflation_power",
        "min_cluster_size",
    ],
    "Post-processing": [
        "revert_threshold_deg",
        "merge_similar_deg",
        "merge_inclusions_max_size",
        "n_vote_iterations",
    ],
}


class ParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._config = ReconstructionConfig()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        preset_row = QComboBox()
        preset_row.addItems(list(_PRESETS))
        preset_row.currentTextChanged.connect(self._apply_preset)
        layout.addWidget(QLabel("Preset:"))
        layout.addWidget(preset_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._form = self._config.to_widget(self)
        self._apply_tooltips()
        self._form.setMinimumHeight(self._form.sizeHint().height())
        self._scroll.setWidget(self._form)
        layout.addWidget(self._scroll)

    def _apply_preset(self, name: str):
        preset = _PRESETS.get(name)
        if preset is None:
            return
        self._config = preset
        old_form = self._form
        self._form = self._config.to_widget(self)
        self._apply_tooltips()
        self._form.setMinimumHeight(self._form.sizeHint().height())
        self._scroll.setWidget(self._form)
        old_form.deleteLater()

    def _apply_tooltips(self):
        from pagb_reconstruction.ui.model_widget import ModelFormWidget

        if not isinstance(self._form, ModelFormWidget):
            return
        for name, widget in self._form._field_widgets.items():
            field_info = type(self._config).model_fields.get(name)
            if field_info and field_info.description:
                widget.setToolTip(field_info.description)

    def get_config(self) -> ReconstructionConfig:
        return self._form.to_model()
