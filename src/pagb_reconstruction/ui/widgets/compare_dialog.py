"""Compare-approaches dialog.

Runs several reconstruction configurations on the same map and ranks them on the
shared fit metrics (Taylor et al. 2024 compare algorithms this way; Hielscher et
al. 2022 sweep parameters). Selection = preset checkboxes + an optional
one-field sweep ("vary the parameters for the best fit"); results = one row per
run with a parent-map thumbnail, ranked best-fit-first; the chosen run can be
applied as the active reconstruction.
"""

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pagb_reconstruction.core.compare import (
    ComparisonRun,
    compare_configs,
    parent_map_rgb,
    sweep_configs,
)
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionConfig
from pagb_reconstruction.ui.theme import active_theme
from pagb_reconstruction.ui.widgets.param_panel import _PRESETS

_THUMB = 96
_SWEEPABLE = [
    name
    for name, f in ReconstructionConfig.model_fields.items()
    if f.annotation in (int, float)
]


class _CompareWorker(QThread):
    progress = Signal(str, float)
    finished = Signal(object)

    def __init__(self, emap: EBSDMap, named_configs):
        super().__init__()
        self._emap = emap
        self._named = named_configs

    def run(self):
        try:
            runs = compare_configs(
                self._emap, self._named, progress_callback=self.progress.emit
            )
            self.finished.emit(runs)
        except Exception as e:  # surfaced in the dialog, never a crash
            self.progress.emit(f"Error: {e}", -1.0)
            self.finished.emit([])


class CompareDialog(QDialog):
    run_chosen = Signal(object)  # ComparisonRun

    def __init__(self, emap: EBSDMap, base_config: ReconstructionConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare reconstruction approaches")
        self.resize(860, 560)
        self._emap = emap
        self._base = base_config
        self._runs: list[ComparisonRun] = []
        self._worker: _CompareWorker | None = None

        layout = QVBoxLayout(self)

        # ── selection: presets + one-field sweep ──
        presets_row = QHBoxLayout()
        presets_row.addWidget(QLabel("Presets:"))
        self._preset_checks: dict[str, QCheckBox] = {}
        for name in _PRESETS:
            cb = QCheckBox(name)
            cb.setChecked(name in ("Default", "Bainite"))
            self._preset_checks[name] = cb
            presets_row.addWidget(cb)
        presets_row.addStretch()
        layout.addLayout(presets_row)

        sweep_row = QHBoxLayout()
        self._sweep_check = QCheckBox("Sweep")
        sweep_row.addWidget(self._sweep_check)
        self._sweep_field = QComboBox()
        self._sweep_field.addItems(_SWEEPABLE)
        self._sweep_field.setCurrentText("min_parent_size_um")
        sweep_row.addWidget(self._sweep_field)
        sweep_row.addWidget(QLabel("values:"))
        self._sweep_values = QLineEdit("0, 5, 10")
        self._sweep_values.setToolTip("Comma-separated values for the swept field")
        sweep_row.addWidget(self._sweep_values, 1)
        layout.addLayout(sweep_row)

        preview_row = QHBoxLayout()
        self._preview_check = QCheckBox("Fast preview (crop to 150 px)")
        self._preview_check.setChecked(True)
        self._preview_check.setToolTip(
            "Compare on a central crop for quick iteration; re-run the winner on "
            "the full map with the main Run button"
        )
        preview_row.addWidget(self._preview_check)
        preview_row.addStretch()
        self._run_btn = QPushButton("Run comparison")
        self._run_btn.setProperty("primary", True)
        self._run_btn.clicked.connect(self._start)
        preview_row.addWidget(self._run_btn)
        layout.addLayout(preview_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._status = QLabel("")
        layout.addWidget(self._progress)
        layout.addWidget(self._status)

        # ── results, ranked best-fit-first ──
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Map", "Approach", "Parents", "% recon", "Size µm (AW)", "Mean fit"]
        )
        _header_tips = [
            "Reconstructed parent map (IPF colours; grey = unreconstructed)",
            "Preset or swept parameter value",
            "Number of reconstructed parent grains",
            "Share of pixels assigned a parent — higher is better",
            "Area-weighted equivalent circle diameter (µm) — compare to the "
            "expected prior-austenite grain size (15–50 µm)",
            "Mean deviation from the ideal orientation relationship (°) — "
            "lower is better",
        ]
        for col, tip in enumerate(_header_tips):
            self._table.horizontalHeaderItem(col).setToolTip(tip)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setColumnWidth(0, _THUMB + 8)
        layout.addWidget(self._table, 1)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self._apply_btn = QPushButton("Use selected result")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_selected)
        apply_row.addWidget(self._apply_btn)
        layout.addLayout(apply_row)

    # ── config selection ──
    def _named_configs(self) -> list[tuple[str, ReconstructionConfig]]:
        named = [
            (name, _PRESETS[name])
            for name, cb in self._preset_checks.items()
            if cb.isChecked()
        ]
        if self._sweep_check.isChecked():
            field = self._sweep_field.currentText()
            try:
                values = [
                    float(v) for v in self._sweep_values.text().split(",") if v.strip()
                ]
            except ValueError:
                values = []
            named += sweep_configs(self._base, field, values)
        return named

    def _target_map(self, max_side: int = 150) -> EBSDMap:
        """Central crop for fast preview; the full map otherwise."""
        rows, cols = self._emap.shape
        if max(rows, cols) <= max_side:
            return self._emap
        r0 = max((rows - max_side) // 2, 0)
        c0 = max((cols - max_side) // 2, 0)
        sub = self._emap.crystal_map[r0 : r0 + max_side, c0 : c0 + max_side]
        return EBSDMap(crystal_map=sub, phases=self._emap.phases)

    # ── run ──
    def _start(self):
        named = self._named_configs()
        if not named:
            self._status.setText("Select at least one preset or sweep value.")
            return
        target = self._target_map() if self._preview_check.isChecked() else self._emap
        self._run_btn.setEnabled(False)
        self._status.setText(f"Comparing {len(named)} approaches…")
        self._worker = _CompareWorker(target, named)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, msg: str, frac: float):
        if frac >= 0:
            self._progress.setValue(int(frac * 100))
        self._status.setText(msg)

    def _on_finished(self, runs: list[ComparisonRun]):
        self._run_btn.setEnabled(True)
        self._worker = None
        if runs:
            self._progress.setValue(100)
            self._status.setText(
                f"{len(runs)} approaches compared — best fit first. Lower mean fit "
                "= closer to the ideal OR; check size against the expected grains."
            )
        self._populate_results(runs)

    # ── results ──
    def _populate_results(self, runs: list[ComparisonRun]):
        self._runs = sorted(runs, key=lambda r: r.quality.mean_fit_deg)
        self._table.setRowCount(len(self._runs))
        accent = QColor(active_theme().accent)
        accent.setAlpha(40)
        for row, run in enumerate(self._runs):
            thumb = QLabel()
            thumb.setPixmap(self._thumbnail(run))
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 0, thumb)
            q = run.quality
            cells = [
                run.name,
                str(q.n_parents),
                f"{q.pct_reconstructed:.0f}%",
                f"{q.area_weighted_ecd_um:.1f}",
                f"{q.mean_fit_deg:.2f}°",
            ]
            for col, text in enumerate(cells, start=1):
                item = QTableWidgetItem(text)
                if row == 0:  # best fit highlighted
                    item.setBackground(accent)
                self._table.setItem(row, col, item)
            self._table.setRowHeight(row, _THUMB + 8)
        self._apply_btn.setEnabled(bool(self._runs))

    def _thumbnail(self, run: ComparisonRun) -> QPixmap:
        emap = (
            self._target_map()
            if self._preview_check.isChecked()
            else self._emap
        )
        # thumbnail must match the map the run was computed on
        if run.result.parent_grain_ids.size != emap.crystal_map.size:
            emap = self._emap
        rgb = (parent_map_rgb(emap, run.result) * 255).astype(np.uint8)
        rgb = np.ascontiguousarray(rgb)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(img).scaled(
            _THUMB,
            _THUMB,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _apply_selected(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._runs):
            self.run_chosen.emit(self._runs[row])
            self.accept()
