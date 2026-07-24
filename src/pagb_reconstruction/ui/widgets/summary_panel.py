"""Headline numbers and the grain-size measurement tool.

Split out of the Statistics panel. Sharing one dock with the charts starved
them: the stat cards plus this measurement group consume more than the whole
default bottom-dock height, so whichever went second never rendered. Capping the
header instead hid the Measure button behind ~800px of content in a 180px
window. Neither block is small enough to budget against the other, so each owns
its own tab.
"""

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.grain_metrics import GrainMetrics
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.widgets.stats_dashboard import StatCard
from pagb_reconstruction.ui.widgets.wheel_guard import install_wheel_guard


class SummaryPanel(QWidget):
    """Stat cards + the grain-size measurement tool."""

    # Test-line geometry to draw on the map (lines, xs, ys), and a clear signal —
    # so the measurement's lines + intercepts are visible + checkable (#15).
    measurement_overlay = Signal(object, object, object)
    measurement_cleared = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._grain_metrics = GrainMetrics()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        self._card_parents = StatCard("Parents")
        self._card_coarsening = StatCard("Coarsening")
        self._card_fit = StatCard("Mean Fit")
        self._card_recon = StatCard("% Recon")
        self._card_time = StatCard("Time")
        for card in (
            self._card_parents,
            self._card_coarsening,
            self._card_fit,
            self._card_recon,
            self._card_time,
        ):
            cards_row.addWidget(card)
        cards_row.addStretch()
        layout.addLayout(cards_row)

        metrics_group = QGroupBox("Grain Size Measurement")
        metrics_layout = QVBoxLayout(metrics_group)
        self._metrics_form = self._grain_metrics.to_widget()
        self._metrics_form.changed.connect(self._on_params_changed)
        metrics_layout.addWidget(self._metrics_form)
        self._sync_field_enablement()  # "Test lines" only applies to intercept
        btn_row = QHBoxLayout()
        self._measure_btn = QPushButton("Measure")
        self._measure_btn.clicked.connect(lambda: self._run_measurement(draw=True))
        self._measure_btn.setEnabled(False)
        btn_row.addWidget(self._measure_btn)
        btn_row.addStretch()
        metrics_layout.addLayout(btn_row)
        self._metrics_label = QLabel("")
        self._metrics_label.setWordWrap(True)
        metrics_layout.addWidget(self._metrics_label)
        layout.addWidget(metrics_group)
        layout.addStretch()

        # The form's combo and spin boxes would otherwise eat the wheel and stall
        # this scroll area with no feedback.
        install_wheel_guard(self)

    def update_stats(
        self,
        result: ReconstructionResult,
        ebsd_map: EBSDMap | None = None,
        elapsed: float = 0.0,
    ) -> None:
        self._result = result
        self._ebsd_map = ebsd_map
        self._measure_btn.setEnabled(result is not None)

        parent_ids = result.parent_grain_ids
        unique_parents = np.unique(parent_ids[parent_ids >= 0])
        n_parents = len(unique_parents)
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        mean_fit = float(np.mean(fit_valid)) if len(fit_valid) > 0 else 0.0
        pct_recon = float(np.sum(parent_ids >= 0) / max(len(parent_ids), 1) * 100)

        self._card_parents.set_value(str(n_parents))
        n_child = len(ebsd_map.grains) if ebsd_map and ebsd_map.grains else 0
        self._card_coarsening.set_value(
            f"{n_child / n_parents:.1f}x" if n_parents and n_child else "-"
        )
        self._card_fit.set_value(f"{mean_fit:.2f}°")
        self._card_recon.set_value(f"{pct_recon:.1f}%")
        self._card_time.set_value(f"{elapsed:.1f}s" if elapsed > 0 else "-")

        # A fresh reconstruction: update the number, but the previous run's test
        # lines are stale — clear them until the user clicks Measure again.
        self._run_measurement(draw=False)

    def _on_params_changed(self) -> None:
        # Settings edited since the last Measure — the drawn lines + shown number
        # are stale. Clear the overlay and say so, rather than leaving a number
        # that no longer matches the controls (Eloïse #15 finding B).
        self._sync_field_enablement()
        self.measurement_cleared.emit()
        if self._metrics_label.text():
            self._metrics_label.setText("Settings changed — click Measure to update.")

    def _sync_field_enablement(self) -> None:
        # "Test lines" is an intercept-only control — grey it out for the area
        # method, where it has no effect (visual-critic finding #2).
        n_lines = self._metrics_form._field_widgets.get("n_lines")
        if n_lines is not None:
            n_lines.setEnabled(self._metrics_form.to_model().method == "intercept")

    def _run_measurement(self, draw: bool = False) -> None:
        if self._result is None or self._ebsd_map is None:
            return
        self._grain_metrics = self._metrics_form.to_model()
        # _to_grid, not reshape: on a hexagonal scan the measured points do not
        # fill the grid, so reshape raises and Qt swallows it (issue #11,
        # "l'outil measure ne marche pas").
        grain_map = self._ebsd_map._to_grid(self._result.parent_grain_ids, fill=-1)
        # (dy, dx) — the map's anisotropic pixel pitch. A hex scan has dx != dy,
        # so a single step scaled every distance wrong (Eloïse #15).
        step_size = self._ebsd_map.step_size

        if self._grain_metrics.method == "intercept":
            gr, lines, xs, ys = self._grain_metrics.measure_intercept(grain_map, step_size)
            if draw:
                self.measurement_overlay.emit(lines, xs, ys)
            else:
                self.measurement_cleared.emit()
        else:
            gr = self._grain_metrics.measure(grain_map, step_size)
            self.measurement_cleared.emit()

        # Compact 3 lines (5 clipped off-screen), worded PER METHOD — the area
        # method has no intercept crossings, so the old shared template showed an
        # alarming "0 crossings over 0.0 µm" (visual-critic finding #1).
        if gr.method == "area":
            self._metrics_label.setText(
                f"Mean grain size: {gr.equivalent_diameter_um:.2f} µm   (ASTM #{gr.astm_grain_size_number:.1f})\n"
                f"equivalent-circle diameter\n"
                f"{gr.grain_count} grains · area"
            )
        else:
            self._metrics_label.setText(
                f"Mean intercept: {gr.mean_intercept_um:.2f} µm   (ASTM #{gr.astm_grain_size_number:.1f})\n"
                f"{gr.total_crossings} crossings over {gr.total_line_length_um:.1f} µm\n"
                f"{gr.grain_count} grains · intercept"
            )
