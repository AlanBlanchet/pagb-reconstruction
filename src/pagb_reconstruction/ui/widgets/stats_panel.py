import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult


class StatsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self._summary_label = QLabel("No data loaded")
        layout.addWidget(self._summary_label)

        self._figure = Figure(figsize=(6, 3))
        self._canvas = FigureCanvasQTAgg(self._figure)
        layout.addWidget(self._canvas)

    def update_stats(
        self, result: ReconstructionResult, ebsd_map: EBSDMap | None = None
    ):
        parent_ids = result.parent_grain_ids
        unique_parents = np.unique(parent_ids[parent_ids >= 0])
        n_parents = len(unique_parents)

        sizes = []
        for pid in unique_parents:
            sizes.append(int(np.sum(parent_ids == pid)))

        mean_size = np.mean(sizes) if sizes else 0
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        mean_fit = np.mean(fit_valid) if len(fit_valid) > 0 else 0

        self._summary_label.setText(
            f"Parent grains: {n_parents} | "
            f"Mean size: {mean_size:.0f} px | "
            f"Mean fit: {mean_fit:.2f}°"
        )

        self._figure.clear()
        if sizes:
            ax1 = self._figure.add_subplot(121)
            ax1.hist(
                sizes, bins=30, color="steelblue", edgecolor="black", linewidth=0.5
            )
            ax1.set_xlabel("Parent grain size (px)")
            ax1.set_ylabel("Count")
            ax1.set_title("Size distribution")

        if len(fit_valid) > 0:
            ax2 = self._figure.add_subplot(122)
            ax2.hist(
                fit_valid, bins=50, color="coral", edgecolor="black", linewidth=0.5
            )
            ax2.set_xlabel("Fit angle (°)")
            ax2.set_ylabel("Count")
            ax2.set_title("Fit quality")

        self._figure.tight_layout()
        self._canvas.draw()
