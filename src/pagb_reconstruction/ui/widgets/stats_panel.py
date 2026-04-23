import numpy as np
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.grain_metrics import GrainMetrics
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.theme import (
    ACCENT,
    DARK_BG,
    DARK_FG,
    EDGE_COLOR,
    GRID_COLOR,
    create_dark_figure,
    style_ax,
)


def mackenzie_pdf(theta_deg: np.ndarray) -> np.ndarray:
    t = np.radians(theta_deg)
    ct = np.cos(t)
    st = np.sin(t)
    ct2 = ct * ct
    st2 = st * st
    denom1 = 1 - ct + 1e-30
    arg1 = np.clip((ct2 - ct) / denom1, -1.0, 1.0)
    arg2 = np.clip((3 * ct2 - 2 * ct - 1) / (denom1**2), -1.0, 1.0)
    term = np.where(
        theta_deg <= 45.0,
        (
            (2.0 / (15.0 * np.pi))
            * (1 - ct)
            * (
                2 * (1 - ct)
                + (4 * st2 - 1) * np.arccos(arg1)
                + (3 * ct - 1) * np.arccos(arg2)
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
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._summary_label = QLabel("No data loaded")
        self._summary_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._summary_label)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        grain_tab = QWidget()
        grain_layout = QVBoxLayout(grain_tab)
        grain_layout.setContentsMargins(4, 4, 4, 4)

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
        grain_layout.addWidget(metrics_group)

        self._cumulative_cb = QCheckBox("Cumulative distribution")
        grain_layout.addWidget(self._cumulative_cb)

        self._grain_fig, self._grain_canvas = create_dark_figure()
        grain_layout.addWidget(self._grain_canvas, 1)
        self._tabs.addTab(grain_tab, "Grain Size")

        misori_tab = QWidget()
        misori_layout = QVBoxLayout(misori_tab)
        misori_layout.setContentsMargins(4, 4, 4, 4)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Phase:"))
        self._phase_filter = QComboBox()
        self._phase_filter.addItem("All phases")
        filter_row.addWidget(self._phase_filter)
        filter_row.addStretch()
        misori_layout.addLayout(filter_row)

        self._misori_fig, self._misori_canvas = create_dark_figure()
        misori_layout.addWidget(self._misori_canvas, 1)
        self._tabs.addTab(misori_tab, "Misorientation")

        variant_tab = QWidget()
        variant_layout = QVBoxLayout(variant_tab)
        variant_layout.setContentsMargins(4, 4, 4, 4)
        self._variant_fig, self._variant_canvas = create_dark_figure()
        variant_layout.addWidget(self._variant_canvas, 1)
        self._tabs.addTab(variant_tab, "Variants")

    def update_stats(
        self, result: ReconstructionResult, ebsd_map: EBSDMap | None = None
    ):
        self._result = result
        self._ebsd_map = ebsd_map
        self._measure_btn.setEnabled(result is not None)

        if ebsd_map is not None:
            self._phase_filter.clear()
            self._phase_filter.addItem("All phases")
            for p in ebsd_map.phases:
                self._phase_filter.addItem(p.name)

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
        self._plot_grain_size(sizes)
        self._plot_misorientation(fit_valid)
        self._plot_variants(result)

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

    def _plot_grain_size(self, sizes: list[int]):
        self._grain_fig.clear()
        ax = self._grain_fig.add_subplot(111)
        style_ax(ax)
        if sizes:
            cumulative = self._cumulative_cb.isChecked()
            ax.hist(
                sizes,
                bins=30,
                color=ACCENT,
                edgecolor=EDGE_COLOR,
                linewidth=0.5,
                cumulative=cumulative,
                density=cumulative,
            )
        ax.set_xlabel("Parent grain size (px)")
        ax.set_ylabel("CDF" if self._cumulative_cb.isChecked() else "Count")
        ax.set_title("Grain Size Distribution")
        self._grain_fig.tight_layout()
        self._grain_canvas.draw()

    def _plot_misorientation(self, fit_valid: np.ndarray):
        self._misori_fig.clear()

        ax1 = self._misori_fig.add_subplot(121)
        style_ax(ax1)
        if len(fit_valid) > 0:
            ax1.hist(
                fit_valid, bins=50, color="#fab387", edgecolor=EDGE_COLOR, linewidth=0.5
            )
        ax1.set_xlabel("Fit angle (\u00b0)")
        ax1.set_ylabel("Count")
        ax1.set_title("Fit Quality")

        ax2 = self._misori_fig.add_subplot(122)
        style_ax(ax2)
        if self._ebsd_map is not None:
            misori_map = self._ebsd_map.compute_map_property("Misorientation")
            angles = misori_map[misori_map > 0].ravel()
            if len(angles) > 0:
                ax2.hist(
                    angles,
                    bins=80,
                    range=(0, 63),
                    density=True,
                    color="#a6e3a1",
                    edgecolor=EDGE_COLOR,
                    linewidth=0.3,
                    alpha=0.7,
                    label="Measured",
                )
                theta = np.linspace(0.1, 62.8, 300)
                pdf = mackenzie_pdf(theta)
                ax2.plot(
                    theta,
                    pdf,
                    color="#f38ba8",
                    linewidth=1.5,
                    label="Mackenzie (cubic)",
                )
                ax2.legend(
                    fontsize=7,
                    facecolor=DARK_BG,
                    edgecolor=GRID_COLOR,
                    labelcolor=DARK_FG,
                )
        ax2.set_xlabel("Misorientation angle (\u00b0)")
        ax2.set_ylabel("Density")
        ax2.set_title("Misorientation Histogram")

        self._misori_fig.tight_layout()
        self._misori_canvas.draw()

    def _plot_variants(self, result: ReconstructionResult):
        self._variant_fig.clear()
        ax = self._variant_fig.add_subplot(111)
        style_ax(ax)
        vids = result.variant_ids
        valid = vids[vids >= 0]
        if len(valid) > 0:
            max_v = int(valid.max()) + 1
            counts = np.bincount(valid, minlength=max_v)
            ax.bar(
                range(max_v),
                counts,
                color="#cba6f7",
                edgecolor=EDGE_COLOR,
                linewidth=0.3,
            )
            ax.set_xticks(range(0, max_v, max(1, max_v // 8)))
        ax.set_xlabel("Variant ID")
        ax.set_ylabel("Pixel count")
        ax.set_title("Variant Distribution")
        self._variant_fig.tight_layout()
        self._variant_canvas.draw()
