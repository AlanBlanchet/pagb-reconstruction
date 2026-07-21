"""Headline numbers and the grain-size measurement tool.

Split out of the Statistics panel. Sharing one dock with the charts starved
them: the stat cards plus this measurement group consume more than the whole
default bottom-dock height, so whichever went second never rendered. Capping the
header instead hid the Measure button behind ~800px of content in a 180px
window. Neither block is small enough to budget against the other, so each owns
its own tab.
"""

import numpy as np
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
        metrics_layout.addWidget(self._metrics_form)
        btn_row = QHBoxLayout()
        self._measure_btn = QPushButton("Measure")
        self._measure_btn.clicked.connect(self._run_measurement)
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

        self._run_measurement()

    def _run_measurement(self) -> None:
        if self._result is None or self._ebsd_map is None:
            return
        self._grain_metrics = self._metrics_form.to_model()
        # _to_grid, not reshape: on a hexagonal scan the measured points do not
        # fill the grid, so reshape raises and Qt swallows it (issue #11,
        # "l'outil measure ne marche pas").
        grain_map = self._ebsd_map._to_grid(self._result.parent_grain_ids, fill=-1)
        step = float(self._ebsd_map.step_size[0])
        gr = self._grain_metrics.measure(grain_map, step_size=step)
        self._metrics_label.setText(
            f"Mean intercept: {gr.mean_intercept_um:.2f} µm\n"
            f"ASTM grain size #: {gr.astm_grain_size_number:.1f}\n"
            f"Grain count: {gr.grain_count}\n"
            f"Method: {gr.method}"
        )
