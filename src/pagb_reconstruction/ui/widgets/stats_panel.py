import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.grain_metrics import GrainMetrics
from pagb_reconstruction.core.reconstruction import ReconstructionResult


def mackenzie_pdf(theta_deg: np.ndarray) -> np.ndarray:
    t = np.radians(theta_deg)
    ct = np.cos(t)
    st = np.sin(t)
    ct2 = ct * ct
    st2 = st * st
    sqrt2 = np.sqrt(2.0)
    term = np.where(
        theta_deg <= 45.0,
        (
            (2.0 / (15.0 * np.pi))
            * (1 - ct)
            * (
                2 * (1 - ct)
                + (4 * st2 - 1) * np.arccos((ct2 - ct) / (1 - ct + 1e-30))
                + (3 * ct - 1) * np.arccos(((3 * ct2 - 2 * ct - 1)) / ((1 - ct) ** 2 + 1e-30))
            )
        ),
        0.0,
    )
    scale = np.trapezoid(term, theta_deg) if len(theta_deg) > 1 else 1.0
    return term / max(scale, 1e-30)


class StatsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result: ReconstructionResult | None = None
        self._grain_metrics = GrainMetrics()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self._summary_label = QLabel("No data loaded")
        layout.addWidget(self._summary_label)

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

        self._figure = Figure(figsize=(8, 6))
        self._canvas = FigureCanvasQTAgg(self._figure)
        layout.addWidget(self._canvas)

    def update_stats(
        self, result: ReconstructionResult, ebsd_map: EBSDMap | None = None
    ):
        self._result = result
        self._ebsd_map = ebsd_map
        self._measure_btn.setEnabled(result is not None)

        parent_ids = result.parent_grain_ids
        unique_parents = np.unique(parent_ids[parent_ids >= 0])
        n_parents = len(unique_parents)

        sizes = [int(np.sum(parent_ids == pid)) for pid in unique_parents]
        mean_size = np.mean(sizes) if sizes else 0
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        mean_fit = np.mean(fit_valid) if len(fit_valid) > 0 else 0

        self._summary_label.setText(
            f"Parent grains: {n_parents} | "
            f"Mean size: {mean_size:.0f} px | "
            f"Mean fit: {mean_fit:.2f}\u00b0"
        )

        self._run_measurement()
        self._plot(sizes, fit_valid, result)

    def _run_measurement(self):
        if self._result is None or self._ebsd_map is None:
            return
        self._grain_metrics = self._metrics_form.to_model()
        grain_map = self._result.parent_grain_ids.reshape(self._ebsd_map.shape)
        step = float(self._ebsd_map.step_size[0])
        gr = self._grain_metrics.measure(grain_map, step_size=step)
        self._metrics_label.setText(
            f"Mean intercept: {gr.mean_intercept_um:.2f} \u00b5m\n"
            f"ASTM grain size #: {gr.astm_grain_size_number:.1f}\n"
            f"Grain count: {gr.grain_count}\n"
            f"Method: {gr.method}"
        )

    def _plot(
        self,
        sizes: list[int],
        fit_valid: np.ndarray,
        result: ReconstructionResult,
    ):
        self._figure.clear()

        ax1 = self._figure.add_subplot(221)
        if sizes:
            ax1.hist(sizes, bins=30, color="steelblue", edgecolor="black", linewidth=0.5)
        ax1.set_xlabel("Parent grain size (px)")
        ax1.set_ylabel("Count")
        ax1.set_title("Size distribution")

        ax2 = self._figure.add_subplot(222)
        if len(fit_valid) > 0:
            ax2.hist(fit_valid, bins=50, color="coral", edgecolor="black", linewidth=0.5)
        ax2.set_xlabel("Fit angle (\u00b0)")
        ax2.set_ylabel("Count")
        ax2.set_title("Fit quality")

        ax3 = self._figure.add_subplot(223)
        if self._ebsd_map is not None:
            misori_map = self._ebsd_map.compute_map_property("Misorientation")
            angles = misori_map[misori_map > 0].ravel()
            if len(angles) > 0:
                ax3.hist(
                    angles, bins=80, range=(0, 63), density=True,
                    color="mediumseagreen", edgecolor="black", linewidth=0.3, alpha=0.7,
                    label="Measured",
                )
                theta = np.linspace(0.1, 62.8, 300)
                pdf = mackenzie_pdf(theta)
                ax3.plot(theta, pdf, "r-", linewidth=1.5, label="Mackenzie (cubic)")
                ax3.legend(fontsize=7)
        ax3.set_xlabel("Misorientation angle (\u00b0)")
        ax3.set_ylabel("Density")
        ax3.set_title("Misorientation histogram")

        ax4 = self._figure.add_subplot(224)
        vids = result.variant_ids
        valid = vids[vids >= 0]
        if len(valid) > 0:
            max_v = int(valid.max()) + 1
            counts = np.bincount(valid, minlength=max_v)
            ax4.bar(range(max_v), counts, color="mediumpurple", edgecolor="black", linewidth=0.3)
            ax4.set_xticks(range(0, max_v, max(1, max_v // 8)))
        ax4.set_xlabel("Variant ID")
        ax4.set_ylabel("Pixel count")
        ax4.set_title("Variant distribution")

        self._figure.tight_layout()
        self._canvas.draw()
