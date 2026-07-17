import warnings

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from pagb_reconstruction.core.updater import UpdateDownloader, relaunch_from


class UpdateBar(QWidget):
    dismissed = Signal()
    open_url = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._downloader: UpdateDownloader | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._label = QLabel("")
        layout.addWidget(self._label)
        layout.addStretch()

        self._progress = QProgressBar()
        self._progress.setObjectName("updateProgress")
        self._progress.setFixedWidth(120)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._download_btn = QPushButton("Update")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._download_btn)

        self._dismiss_btn = QPushButton("\u2715")
        self._dismiss_btn.setObjectName("dismissBtn")
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self._dismiss_btn)

        self._url = ""
        self._download_url = ""

    def _safe_disconnect(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self._download_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass

    def show_update(self, version: str, url: str, download_url: str = ""):
        self._label.setText(f"Update available: v{version}")
        self._url = url
        self._download_url = download_url
        self._safe_disconnect()
        if download_url:
            self._download_btn.setText("Update")
            self._download_btn.clicked.connect(self._start_download)
        else:
            self._download_btn.setText("Download")
            self._download_btn.clicked.connect(lambda: self.open_url.emit(url))
        self.setVisible(True)

    def _start_download(self):
        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading...")
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._downloader = UpdateDownloader(self._download_url)
        self._downloader.progress.connect(self._progress.setValue)
        self._downloader.finished.connect(self._on_downloaded)
        self._downloader.error.connect(self._on_download_error)
        self._downloader.start()

    def _on_downloaded(self, binary_path: str):
        self._label.setText("Update downloaded — restarting...")
        self._progress.setVisible(False)
        self._download_btn.setVisible(False)
        self._dismiss_btn.setVisible(False)
        relaunch_from(binary_path)

    def _on_download_error(self, msg: str):
        self._label.setText(f"Update failed: {msg}")
        self._download_btn.setEnabled(True)
        self._download_btn.setText("Retry")
        self._progress.setVisible(False)
        self._safe_disconnect()
        self._download_btn.clicked.connect(self._start_download)

    def _on_dismiss(self):
        self.setVisible(False)
        self.dismissed.emit()
