import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QComboBox, QFormLayout, QVBoxLayout, QWidget


class PoleFigureWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        controls = QFormLayout()
        self._hkl_combo = QComboBox()
        self._hkl_combo.addItems(["(001)", "(011)", "(111)"])
        self._hkl_combo.currentTextChanged.connect(self._replot)
        controls.addRow("Plane:", self._hkl_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Child", "Parent"])
        self._mode_combo.currentTextChanged.connect(self._replot)
        controls.addRow("Mode:", self._mode_combo)
        layout.addLayout(controls)

        self._figure = Figure(figsize=(4, 4))
        self._canvas = FigureCanvasQTAgg(self._figure)
        layout.addWidget(self._canvas)

        self._orientations: np.ndarray | None = None

    def set_orientations(self, quaternions: np.ndarray):
        self._orientations = quaternions
        self._replot()

    def _replot(self):
        self._figure.clear()
        ax = self._figure.add_subplot(111, projection="polar")
        ax.set_title(f"Pole Figure {self._hkl_combo.currentText()}")

        if self._orientations is not None and len(self._orientations) > 0:
            from orix.quaternion import Orientation
            from orix.vector import Vector3d

            hkl_map = {"(001)": (0, 0, 1), "(011)": (0, 1, 1), "(111)": (1, 1, 1)}
            hkl = hkl_map.get(self._hkl_combo.currentText(), (0, 0, 1))
            pole = Vector3d(hkl)

            n_max = min(len(self._orientations), 5000)
            subset = self._orientations[:n_max]
            ori = Orientation(subset)
            rotated = ori * pole
            azimuth = np.arctan2(rotated.data[:, 1], rotated.data[:, 0])
            polar = np.arccos(np.clip(rotated.data[:, 2], -1, 1))

            ax.scatter(azimuth, polar, s=1, alpha=0.3, c="steelblue")

        ax.set_ylim(0, np.pi / 2)
        self._canvas.draw()
