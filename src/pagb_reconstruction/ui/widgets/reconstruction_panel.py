import time

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox,
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
from pagb_reconstruction.ui.theme import ACCENT

_STEP_NAMES = [
    "Detecting grains", "Setting up OR", "Refining OR",
    "Building variant graph", "Building graph", "Clustering variants",
    "Clustering", "Computing parent orientations", "Vote filling",
    "Merging similar", "Merging inclusions", "Computing variants", "Done",
]


class _ReconstructionWorker(QThread):
    progress = Signal(str, float)
    finished = Signal(object)
    step_timed = Signal(str, float)

    def __init__(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        super().__init__()
        self._ebsd_map = ebsd_map
        self._config = config
        self._last_step = ""
        self._last_time = 0.0

    def run(self):
        try:
            self._last_time = time.monotonic()
            engine = ReconstructionEngine(self._ebsd_map, self._config)
            result = engine.run(progress_callback=self._on_progress)
            self.finished.emit(result)
        except Exception as e:
            self.progress.emit(f"Error: {e}", -1.0)
            self.finished.emit(None)

    def _on_progress(self, step: str, pct: float):
        now = time.monotonic()
        if self._last_step:
            self.step_timed.emit(self._last_step, now - self._last_time)
        self._last_step = step
        self._last_time = now
        self.progress.emit(step, pct)


class ReconstructionPanel(QWidget):
    run_requested = Signal()
    reconstruction_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self._worker: _ReconstructionWorker | None = None
        self._start_time = 0.0
        self._step_timings: list[tuple[str, float]] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_layout = QHBoxLayout()
        self._run_btn = QPushButton("Run Reconstruction")
        self._run_btn.clicked.connect(self.run_requested.emit)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        btn_layout.addWidget(self._stop_btn)
        layout.addLayout(btn_layout)

        progress_layout = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 #74c7ec); }}"
        )
        progress_layout.addWidget(self._progress_bar, 1)
        self._step_counter = QLabel("")
        self._step_counter.setMinimumWidth(70)
        progress_layout.addWidget(self._step_counter)
        layout.addLayout(progress_layout)

        self._step_label = QLabel("Idle")
        layout.addWidget(self._step_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(100)
        layout.addWidget(self._log)

        self._results_group = QGroupBox("Results Summary")
        self._results_group.setVisible(False)
        results_layout = QVBoxLayout(self._results_group)
        self._results_label = QLabel("")
        self._results_label.setWordWrap(True)
        results_layout.addWidget(self._results_label)
        layout.addWidget(self._results_group)

    def start_reconstruction(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        if self._worker is not None and self._worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log.clear()
        self._results_group.setVisible(False)
        self._step_timings.clear()
        self._start_time = time.monotonic()

        self._worker = _ReconstructionWorker(ebsd_map, config)
        self._worker.progress.connect(self._on_progress)
        self._worker.step_timed.connect(self._on_step_timed)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, step: str, pct: float):
        self._step_label.setText(step)
        self._log.appendPlainText(step)
        if pct >= 0:
            self._progress_bar.setValue(int(pct * 100))
            step_idx = max(1, int(pct * len(_STEP_NAMES)))
            self._step_counter.setText(f"Step {step_idx}/{len(_STEP_NAMES)}")

    def _on_step_timed(self, step: str, elapsed: float):
        self._step_timings.append((step, elapsed))
        self._log.appendPlainText(f"  \u2192 {step}: {elapsed:.2f}s")

    def _on_finished(self, result: ReconstructionResult | None):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        if result:
            total_time = time.monotonic() - self._start_time
            self._progress_bar.setValue(100)
            self._progress_bar.setStyleSheet(
                "QProgressBar::chunk { background: #a6e3a1; border-radius: 3px; }"
            )
            self._step_label.setText("Done")
            self._step_counter.setText(f"{len(_STEP_NAMES)}/{len(_STEP_NAMES)}")

            n_parents = len(np.unique(result.parent_grain_ids[result.parent_grain_ids >= 0]))
            fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
            mean_fit = float(np.mean(fit_valid)) if len(fit_valid) > 0 else 0
            pct = np.sum(result.parent_grain_ids >= 0) / len(result.parent_grain_ids) * 100

            timing_lines = [f"  {name}: {t:.2f}s" for name, t in self._step_timings]
            self._results_label.setText(
                f"Parent grains: {n_parents}\n"
                f"Mean fit angle: {mean_fit:.2f}\u00b0\n"
                f"Reconstructed: {pct:.1f}%\n"
                f"Total time: {total_time:.1f}s\n\n"
                f"Step timings:\n" + "\n".join(timing_lines)
            )
            self._results_group.setVisible(True)
        else:
            self._progress_bar.setValue(0)
            self._step_label.setText("Failed")
            self._results_group.setVisible(False)

        self.reconstruction_finished.emit(result)
        self._worker = None
