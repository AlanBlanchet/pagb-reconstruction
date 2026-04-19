from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QProgressBar,
    QStatusBar,
    QToolBar,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.io.base import load_ebsd
from pagb_reconstruction.ui.widgets.map_viewer import MapViewer
from pagb_reconstruction.ui.widgets.or_panel import ORPanel
from pagb_reconstruction.ui.widgets.param_panel import ParamPanel
from pagb_reconstruction.ui.widgets.phase_panel import PhasePanel
from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget
from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel
from pagb_reconstruction.ui.widgets.stats_panel import StatsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("PAGB Reconstruction")
        self.setMinimumSize(1200, 800)

        self._map_viewer = MapViewer()
        self.setCentralWidget(self._map_viewer)

        self._param_panel = ParamPanel()
        self._phase_panel = PhasePanel()
        self._or_panel = ORPanel()
        self._reconstruction_panel = ReconstructionPanel()
        self._stats_panel = StatsPanel()
        self._pole_figure = PoleFigureWidget()

        right_min = (280, 200)
        bottom_min = (400, 150)

        dock_params = self._add_dock(
            "Parameters",
            self._param_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )
        dock_phases = self._add_dock(
            "Phases",
            self._phase_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )
        dock_or = self._add_dock(
            "Orientation Relationship",
            self._or_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )

        self.tabifyDockWidget(dock_params, dock_phases)
        self.tabifyDockWidget(dock_phases, dock_or)
        dock_params.raise_()

        dock_recon = self._add_dock(
            "Reconstruction",
            self._reconstruction_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_stats = self._add_dock(
            "Statistics",
            self._stats_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_pole = self._add_dock(
            "Pole Figure",
            self._pole_figure,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )

        self.tabifyDockWidget(dock_recon, dock_stats)
        self.tabifyDockWidget(dock_stats, dock_pole)
        dock_recon.raise_()

        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()

    def _add_dock(
        self,
        title: str,
        widget,
        area: Qt.DockWidgetArea,
        min_size: tuple[int, int] = (200, 150),
    ):
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setObjectName(title.replace(" ", "_"))
        dock.setMinimumSize(*min_size)
        self.addDockWidget(area, dock)
        return dock

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save...", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu_bar.addMenu("&View")
        tools_menu = menu_bar.addMenu("&Tools")

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")
        self.addToolBar(toolbar)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self._open_file)
        toolbar.addAction(open_action)

        run_action = QAction("Run", self)
        run_action.triggered.connect(self._run_reconstruction)
        toolbar.addAction(run_action)

        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self._reset)
        toolbar.addAction(reset_action)

    def _setup_statusbar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("Ready — Open an EBSD file to begin")

    def _connect_signals(self):
        self._reconstruction_panel.run_requested.connect(self._run_reconstruction)
        self._reconstruction_panel.reconstruction_finished.connect(
            self._on_reconstruction_done
        )

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open EBSD File",
            "",
            "EBSD Files (*.ang *.ctf *.h5 *.hdf5 *.h5ebsd);;All Files (*)",
        )
        if not path:
            return
        self._load_file(Path(path))

    def _load_file(self, path: Path):
        try:
            self._ebsd_map = load_ebsd(path)
            self._map_viewer.set_ebsd_map(self._ebsd_map)
            self._phase_panel.set_phases(self._ebsd_map.phases)
            self._status_bar.showMessage(
                f"Loaded: {path.name} — {self._ebsd_map.shape[0]}×{self._ebsd_map.shape[1]} pixels"
            )
        except Exception as e:
            self._status_bar.showMessage(f"Error loading file: {e}")

    def _run_reconstruction(self):
        if self._ebsd_map is None:
            self._status_bar.showMessage("No data loaded")
            return
        config = self._param_panel.get_config()
        or_config = self._or_panel.get_or_type()
        config_dict = config.model_dump()
        config_dict["or_type"] = or_config
        from pagb_reconstruction.core.reconstruction import ReconstructionConfig

        full_config = ReconstructionConfig(**config_dict)
        self._reconstruction_panel.start_reconstruction(self._ebsd_map, full_config)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)

    def _on_reconstruction_done(self, result):
        self._progress_bar.setVisible(False)
        if result is None:
            self._status_bar.showMessage("Reconstruction failed")
            return
        self._map_viewer.set_reconstruction_result(result)
        self._stats_panel.update_stats(result, self._ebsd_map)
        n_parents = len(set(result.parent_grain_ids.tolist()))
        self._status_bar.showMessage(
            f"Reconstruction complete — {n_parents} parent grains"
        )

    def _reset(self):
        self._ebsd_map = None
        self._map_viewer.clear()
        self._status_bar.showMessage("Ready — Open an EBSD file to begin")
