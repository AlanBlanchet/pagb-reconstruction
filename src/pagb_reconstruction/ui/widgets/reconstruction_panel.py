import time

import numpy as np
from PySide6.QtCore import QSize, QThread, Signal
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
from pagb_reconstruction.ui.theme import active_theme

_STEP_NAMES = [
    "Detecting grains",
    "Setting up OR",
    "Refining OR",
    "Building variant graph",
    "Building graph",
    "Clustering variants",
    "Clustering",
    "Computing parent orientations",
    "Vote filling",
    "Merging similar",
    "Merging inclusions",
    "Computing variants",
    "Done",
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
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._last_time = time.monotonic()
            engine = ReconstructionEngine(self._ebsd_map, self._config)
            result = engine.run(progress_callback=self._on_progress)
            self.finished.emit(result)
        except InterruptedError:
            self.progress.emit("Cancelled", -1.0)
            self.finished.emit(None)
        except Exception as e:
            self.progress.emit(f"Error: {e}", -1.0)
            self.finished.emit(None)

    def _on_progress(self, step: str, pct: float):
        if self._cancelled:
            raise InterruptedError("Cancelled by user")
        now = time.monotonic()
        if self._last_step:
            self.step_timed.emit(self._last_step, now - self._last_time)
        self._last_step = step
        self._last_time = now
        self.progress.emit(step, pct)


class _OptimizeWorker(QThread):
    """Runs the parameter sweep off the UI thread (Eloïse #14 auto-optimize)."""

    progress = Signal(str, float)
    finished = Signal(object)

    def __init__(self, ebsd_map: EBSDMap, base_config: ReconstructionConfig):
        super().__init__()
        self._ebsd_map = ebsd_map
        self._base = base_config

    def run(self):
        try:
            from pagb_reconstruction.core.compare import auto_optimize

            ranked = auto_optimize(
                self._ebsd_map, self._base, progress_callback=self.progress.emit
            )
            self.finished.emit(ranked[0] if ranked else None)
        except Exception as e:  # noqa: BLE001 — surface any failure to the panel
            self.progress.emit(f"Error: {e}", -1.0)
            self.finished.emit(None)


class ReconstructionPanel(QWidget):
    run_requested = Signal()
    compare_requested = Signal()
    optimize_requested = Signal()
    reconstruction_finished = Signal(object)
    optimize_finished = Signal(object)

    def __init__(self):
        super().__init__()
        self._worker: _ReconstructionWorker | None = None
        self._opt_worker: _OptimizeWorker | None = None
        self._start_time = 0.0
        self._step_timings: list[tuple[str, float]] = []
        self._config = ReconstructionConfig()
        self._setup_ui()

    def sizeHint(self):
        return QSize(400, 120)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_layout = QHBoxLayout()
        self._run_btn = QPushButton("Run Reconstruction")
        self._run_btn.setProperty("primary", True)
        self._run_btn.clicked.connect(self.run_requested.emit)
        btn_layout.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self._stop_btn)

        self._compare_btn = QPushButton("Compare…")
        self._compare_btn.setToolTip(
            "Run several parameter sets on this map and rank them by fit"
        )
        self._compare_btn.clicked.connect(self.compare_requested.emit)
        btn_layout.addWidget(self._compare_btn)

        self._optimize_btn = QPushButton("Auto-optimize")
        self._optimize_btn.setToolTip(
            "Sweep merge + clustering parameters (boundary smoothing on) and adopt "
            "the best-fitting, most realistically-sized prior-austenite map"
        )
        self._optimize_btn.clicked.connect(self.optimize_requested.emit)
        btn_layout.addWidget(self._optimize_btn)
        layout.addLayout(btn_layout)

        progress_layout = QHBoxLayout()
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        progress_layout.addWidget(self._progress_bar, 1)
        self._step_counter = QLabel("")
        self._step_counter.setMinimumWidth(70)
        progress_layout.addWidget(self._step_counter)
        layout.addLayout(progress_layout)

        self._step_label = QLabel("Idle")
        layout.addWidget(self._step_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(60)
        layout.addWidget(self._log)

        self._results_group = QGroupBox("Results Summary")
        self._results_group.setVisible(False)
        results_layout = QVBoxLayout(self._results_group)
        self._results_label = QLabel("")
        self._results_label.setWordWrap(True)
        results_layout.addWidget(self._results_label)
        layout.addWidget(self._results_group)
        layout.addStretch(1)

    def start_reconstruction(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        if self._worker is not None and self._worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log.clear()
        self._progress_bar.setStyleSheet("")
        self._results_group.setVisible(False)
        self._step_timings.clear()
        self._config = config
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
            # NB: the closing literal is NOT an f-string — "}}" would emit two
            # braces and Qt rejects the whole sheet ("Could not parse stylesheet").
            self._progress_bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: {active_theme().success};"
                " border-radius: 6px; }"
            )
            self._step_label.setText("Done")
            self._step_counter.setText(f"{len(_STEP_NAMES)}/{len(_STEP_NAMES)}")
            self._show_results_summary(result, total_time, self._config)
        else:
            self._progress_bar.setValue(0)
            self._step_label.setText("Failed")
            self._results_group.setVisible(False)

        self.reconstruction_finished.emit(result)
        self._worker = None

    def _show_results_summary(self, result, total_time, config):
        """Populate the Results Summary card \u2014 shared by a manual Run and by
        Auto-optimize (whose card previously never repopulated)."""
        n_parents = len(np.unique(result.parent_grain_ids[result.parent_grain_ids >= 0]))
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        mean_fit = float(np.mean(fit_valid)) if len(fit_valid) > 0 else 0
        max_fit = float(np.max(fit_valid)) if len(fit_valid) > 0 else 0
        tol = config.revert_threshold_deg
        n_poor = int(np.sum(fit_valid > tol)) if len(fit_valid) > 0 else 0
        pct = np.sum(result.parent_grain_ids >= 0) / len(result.parent_grain_ids) * 100
        ok = mean_fit <= tol
        _p = active_theme()
        verdict_color = _p.success if ok else _p.warning
        verdict = "good fit" if ok else "high fit \u2014 check OR"

        self._results_label.setText(
            f"Parent grains: {n_parents}\n"
            f"Mean fit: {mean_fit:.2f}\u00b0  (max {max_fit:.1f}\u00b0, "
            f"{n_poor} px > {tol:.1f}\u00b0 tol)\n"
            f"Reconstructed: {pct:.1f}%\n"
            f"Total time: {total_time:.1f}s"
        )
        self._results_group.setTitle(f"Results Summary \u2014 {verdict}")
        self._results_group.setStyleSheet(f"QGroupBox::title {{ color: {verdict_color}; }}")
        self._results_group.setVisible(True)

    def start_auto_optimize(self, ebsd_map: EBSDMap, base_config: ReconstructionConfig):
        if self._opt_worker is not None and self._opt_worker.isRunning():
            return
        self._run_btn.setEnabled(False)
        self._optimize_btn.setEnabled(False)
        self._compare_btn.setEnabled(False)
        self._log.clear()
        self._log.appendPlainText("Auto-optimize: sweeping parameters…")
        self._progress_bar.setStyleSheet("")
        self._results_group.setVisible(False)
        self._start_time = time.monotonic()

        self._opt_worker = _OptimizeWorker(ebsd_map, base_config)
        self._opt_worker.progress.connect(self._on_progress)
        self._opt_worker.finished.connect(self._on_optimize_finished)
        self._opt_worker.start()

    def _on_optimize_finished(self, best):
        import dataclasses

        self._run_btn.setEnabled(True)
        self._optimize_btn.setEnabled(True)
        self._compare_btn.setEnabled(True)
        if best is not None:
            best = dataclasses.replace(best, name="auto-optimized")
            self._progress_bar.setValue(100)
            self._step_label.setText("Auto-optimize done")
            # Populate the Results Summary card too — not just the status bar.
            self._show_results_summary(
                best.result, time.monotonic() - self._start_time, best.config
            )
        else:
            self._progress_bar.setValue(0)
            self._step_label.setText("Auto-optimize failed")
        self.optimize_finished.emit(best)
        self._opt_worker = None

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
