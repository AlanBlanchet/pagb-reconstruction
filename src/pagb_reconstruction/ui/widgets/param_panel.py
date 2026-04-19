from PySide6.QtWidgets import QVBoxLayout, QWidget

from pagb_reconstruction.core.reconstruction import ReconstructionConfig
from pagb_reconstruction.ui.model_widget import ModelFormWidget


class ParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._config = ReconstructionConfig()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._form = self._config.to_widget(self)
        layout.addWidget(self._form)

    def get_config(self) -> ReconstructionConfig:
        return self._form.to_model()
