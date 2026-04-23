from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class UpdateBar(QWidget):
    dismissed = Signal()
    open_url = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setStyleSheet(
            "background: #1e66f5; color: white; padding: 6px 12px; border-radius: 4px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._label = QLabel("")
        self._label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(self._label)
        layout.addStretch()

        self._download_btn = QPushButton("Download")
        self._download_btn.setStyleSheet(
            "background: white; color: #1e66f5; border-radius: 3px; "
            "padding: 4px 12px; font-weight: bold;"
        )
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._download_btn)

        self._dismiss_btn = QPushButton("\u2715")
        self._dismiss_btn.setStyleSheet(
            "background: transparent; color: white; border: none; font-size: 16px;"
        )
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self._dismiss_btn)

    def show_update(self, version: str, url: str):
        self._label.setText(f"Update available: v{version}")
        try:
            self._download_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._download_btn.clicked.connect(lambda: self.open_url.emit(url))
        self.setVisible(True)

    def _on_dismiss(self):
        self.setVisible(False)
        self.dismissed.emit()
