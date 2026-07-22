import numpy as np
from orix.quaternion import Orientation
from orix.vector import Vector3d
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QVBoxLayout, QWidget
from scipy.stats import gaussian_kde

from pagb_reconstruction.ui.theme import active_theme, create_figure
from pagb_reconstruction.ui.widgets.wheel_guard import block_wheel


class PoleFigureWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        controls = QFormLayout()
        self._hkl_combo = QComboBox()
        self._hkl_combo.addItems(["(001)", "(011)", "(111)"])
        self._hkl_combo.currentTextChanged.connect(self._replot)
        controls.addRow("Plane:", self._hkl_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Child", "Parent"])
        self._mode_combo.currentTextChanged.connect(self._replot)
        controls.addRow("Mode:", self._mode_combo)

        self._contour_cb = QCheckBox("Contour (KDE)")
        self._contour_cb.toggled.connect(self._replot)
        controls.addRow(self._contour_cb)

        layout.addLayout(controls)

        self._figure, self._canvas = create_figure(figsize=(4, 4))
        # A matplotlib canvas has no setMouseEnabled(False); block the wheel so
        # the pole figure never zooms on hover-scroll like the pyqtgraph plots.
        block_wheel(self._canvas)
        layout.addWidget(self._canvas, 1)

        self._child_ori: np.ndarray | None = None
        self._parent_ori: np.ndarray | None = None

    def set_orientations(
        self, child: np.ndarray | None = None, parent: np.ndarray | None = None
    ):
        """Feed both orientation sets so the Child/Parent selector actually
        switches source — before, Mode was wired to replot the same array."""
        self._child_ori = child
        self._parent_ori = parent
        self._replot()

    @property
    def _orientations(self) -> np.ndarray | None:
        parent = self._mode_combo.currentText() == "Parent"
        return self._parent_ori if parent else self._child_ori

    def _replot(self):
        self._figure.clear()
        ax = self._figure.add_subplot(111, projection="polar")
        p = active_theme()
        ax.set_facecolor(p.surface_dim)
        ax.tick_params(colors=p.fg, labelsize=7)
        ax.set_title(
            f"Pole Figure {self._hkl_combo.currentText()}",
            color=p.fg,
            fontsize=10,
            pad=12,
        )

        if self._orientations is not None and len(self._orientations) > 0:
            hkl_map = {"(001)": (0, 0, 1), "(011)": (0, 1, 1), "(111)": (1, 1, 1)}
            hkl = hkl_map.get(self._hkl_combo.currentText(), (0, 0, 1))
            pole = Vector3d(hkl)

            n_max = min(len(self._orientations), 5000)
            subset = self._orientations[:n_max]
            ori = Orientation(subset)
            rotated = ori * pole
            azimuth = np.arctan2(rotated.data[:, 1], rotated.data[:, 0])
            polar = np.arccos(np.clip(rotated.data[:, 2], -1, 1))

            upper = polar <= np.pi / 2
            azimuth = azimuth[upper]
            polar = polar[upper]

            if self._contour_cb.isChecked() and len(azimuth) > 10:
                x = polar * np.cos(azimuth)
                y = polar * np.sin(azimuth)
                try:
                    kde = gaussian_kde(np.vstack([x, y]), bw_method=0.15)
                    xi = np.linspace(-np.pi / 2, np.pi / 2, 80)
                    yi = np.linspace(-np.pi / 2, np.pi / 2, 80)
                    Xi, Yi = np.meshgrid(xi, yi)
                    Ri = np.sqrt(Xi**2 + Yi**2)
                    Ai = np.arctan2(Yi, Xi)
                    Zi = kde(np.vstack([Xi.ravel(), Yi.ravel()])).reshape(Xi.shape)
                    Zi[Ri > np.pi / 2] = np.nan
                    cs = ax.contourf(Ai, Ri, Zi, levels=15, cmap="magma")
                    self._figure.colorbar(cs, ax=ax, pad=0.1, shrink=0.8)
                except np.linalg.LinAlgError:
                    ax.scatter(azimuth, polar, s=1, alpha=0.3, c=p.accent)
            else:
                ax.scatter(azimuth, polar, s=1, alpha=0.3, c=p.accent)

            for label, angle_deg in [("[100]", 0), ("[010]", 90), ("[001]", 0)]:
                ax.annotate(
                    label,
                    xy=(np.radians(angle_deg), np.pi / 2 * 0.95),
                    fontsize=7,
                    color=p.fg,
                    ha="center",
                )

        ax.set_ylim(0, np.pi / 2)
        for spine in ax.spines.values():
            spine.set_color(p.border)
        self._figure.tight_layout()
        self._canvas.draw()
