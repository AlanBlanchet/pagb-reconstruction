from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import (
    ReconstructionConfig,
    ReconstructionEngine,
    ReconstructionResult,
)


class _ReconstructionWorker(QThread):
    progress = Signal(str, float)
    finished = Signal(object)

    def __init__(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        super().__init__()
        self._ebsd_map = ebsd_map
        self._config = config

    def run(self):
        try:
            engine = ReconstructionEngine(self._ebsd_map, self._config)
            result = engine.run(progress_callback=self._on_progress)
            self.finished.emit(result)
        except Exception as e:
            self.progress.emit(f"Error: {e}", -1.0)
            self.finished.emit(None)

    def _on_progress(self, step: str, pct: float):
        self.progress.emit(step, pct)


class ReconstructionPanel(QWidget):
    run_requested = Signal()
    reconstruction_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self._worker: _ReconstructionWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        btn_layout = QHBoxLayout()
        self._run_btn = QPushButton("Run Reconstruction")
        self._run_btn.clicked.connect(self.run_requested.emit)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        btn_layout.addWidget(self._stop_btn)
        layout.addLayout(btn_layout)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        layout.addWidget(self._progress_bar)

        self._step_label = QLabel("Idle")
        layout.addWidget(self._step_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        layout.addWidget(self._log)

    def start_reconstruction(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        if self._worker is not None and self._worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log.clear()

        self._worker = _ReconstructionWorker(ebsd_map, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, step: str, pct: float):
        self._step_label.setText(step)
        self._log.appendPlainText(step)
        if pct >= 0:
            self._progress_bar.setValue(int(pct * 100))

    def _on_finished(self, result: ReconstructionResult | None):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress_bar.setValue(100 if result else 0)
        self._step_label.setText("Done" if result else "Failed")
        self.reconstruction_finished.emit(result)
        self._worker = None
