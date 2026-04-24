from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionConfig
from pagb_reconstruction.core.updater import UpdateChecker
from pagb_reconstruction.io.base import load_ebsd
from pagb_reconstruction.ui.widgets.map_viewer import MapViewer
from pagb_reconstruction.ui.widgets.or_panel import ORPanel
from pagb_reconstruction.ui.widgets.param_panel import ParamPanel
from pagb_reconstruction.ui.widgets.phase_panel import PhasePanel
from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget
from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel
from pagb_reconstruction.ui.widgets.stats_panel import StatsPanel
from pagb_reconstruction.ui.widgets.update_bar import UpdateBar

_MAX_RECENT = 8
_SETTINGS_ORG = "PAGB"
_SETTINGS_APP = "pagb-reconstruction"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._ebsd_map: EBSDMap | None = None
        self._result = None
        self._recon_start = datetime.now()
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self.setAcceptDrops(True)
        self._setup_ui()
        self._restore_state()
        if not self._settings.contains("window_geometry"):
            self.showMaximized()

    def _setup_ui(self):
        self.setWindowTitle("PAGB Reconstruction")
        self.setMinimumSize(1200, 800)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self._update_bar = UpdateBar()
        central_layout.addWidget(self._update_bar)

        self._map_viewer = MapViewer()
        central_layout.addWidget(self._map_viewer, 1)
        self.setCentralWidget(central)

        self._param_panel = ParamPanel()
        self._phase_panel = PhasePanel()
        self._or_panel = ORPanel()
        self._reconstruction_panel = ReconstructionPanel()
        self._stats_panel = StatsPanel()
        self._pole_figure = PoleFigureWidget()

        self._grain_info = QWidget()
        self._grain_form = QFormLayout(self._grain_info)
        self._grain_labels: dict[str, QLabel] = {}
        for field in (
            "Grain ID",
            "Phase",
            "Area (px)",
            "Eq. Diameter",
            "Aspect Ratio",
            "Mean Orientation",
            "Neighbors",
            "Parent Grain ID",
            "Variant ID",
            "Fit Angle",
        ):
            label = QLabel("-")
            label.setWordWrap(True)
            self._grain_labels[field] = label
            self._grain_form.addRow(f"{field}:", label)

        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)

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
        dock_grain_info = self._add_dock(
            "Grain Info",
            self._grain_info,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )

        self.tabifyDockWidget(dock_params, dock_phases)
        self.tabifyDockWidget(dock_phases, dock_or)
        self.tabifyDockWidget(dock_or, dock_grain_info)
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
        dock_log = self._add_dock(
            "Log",
            self._log_text,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )

        self.tabifyDockWidget(dock_recon, dock_stats)
        self.tabifyDockWidget(dock_stats, dock_pole)
        self.tabifyDockWidget(dock_pole, dock_log)
        dock_recon.raise_()

        self._docks = {
            "Parameters": dock_params,
            "Phases": dock_phases,
            "Orientation Relationship": dock_or,
            "Grain Info": dock_grain_info,
            "Reconstruction": dock_recon,
            "Statistics": dock_stats,
            "Pole Figure": dock_pole,
            "Log": dock_log,
        }

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
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)

        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu_bar.addMenu("&View")
        for name, dock in self._docks.items():
            action = dock.toggleViewAction()
            action.setText(name)
            view_menu.addAction(action)

        tools_menu = menu_bar.addMenu("&Tools")
        export_img = QAction("Export Image (PNG/SVG)...", self)
        export_img.triggered.connect(self._export_image)
        tools_menu.addAction(export_img)

        export_stats = QAction("Export Stats (CSV)...", self)
        export_stats.triggered.connect(self._export_stats)
        tools_menu.addAction(export_stats)

        export_data = QAction("Export Map Data...", self)
        export_data.triggered.connect(self._export_map_data)
        tools_menu.addAction(export_data)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")
        self.addToolBar(toolbar)

        style = self.style()

        open_action = QAction(
            style.standardIcon(style.StandardPixmap.SP_DialogOpenButton), "Open", self
        )
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_file)
        toolbar.addAction(open_action)

        save_action = QAction(
            style.standardIcon(style.StandardPixmap.SP_DialogSaveButton), "Save", self
        )
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_file)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        run_action = QAction(
            style.standardIcon(style.StandardPixmap.SP_MediaPlay), "Run", self
        )
        run_action.setShortcut(QKeySequence("Ctrl+R"))
        run_action.triggered.connect(self._run_reconstruction)
        toolbar.addAction(run_action)

        self._stop_action = QAction(
            style.standardIcon(style.StandardPixmap.SP_MediaStop), "Stop", self
        )
        self._stop_action.setShortcut(QKeySequence("Escape"))
        toolbar.addAction(self._stop_action)

        toolbar.addSeparator()

        zoom_in = QAction(
            style.standardIcon(style.StandardPixmap.SP_ArrowUp), "Zoom In", self
        )
        zoom_in.triggered.connect(lambda: self._map_viewer.zoom(1.25))
        toolbar.addAction(zoom_in)

        zoom_out = QAction(
            style.standardIcon(style.StandardPixmap.SP_ArrowDown), "Zoom Out", self
        )
        zoom_out.triggered.connect(lambda: self._map_viewer.zoom(0.8))
        toolbar.addAction(zoom_out)

        zoom_fit = QAction(
            style.standardIcon(style.StandardPixmap.SP_TitleBarMaxButton), "Fit", self
        )
        zoom_fit.triggered.connect(self._map_viewer.zoom_fit)
        toolbar.addAction(zoom_fit)

        toolbar.addSeparator()

        export_img = QAction(
            style.standardIcon(style.StandardPixmap.SP_DesktopIcon),
            "Export Image",
            self,
        )
        export_img.triggered.connect(self._export_image)
        toolbar.addAction(export_img)

        export_data = QAction(
            style.standardIcon(style.StandardPixmap.SP_FileIcon), "Export Data", self
        )
        export_data.triggered.connect(self._export_map_data)
        toolbar.addAction(export_data)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Display: "))
        toolbar.addWidget(self._map_viewer._display_combo)
        toolbar.addWidget(self._map_viewer._hist_eq_cb)

        toolbar.addSeparator()

        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems(
            ["viridis", "plasma", "magma", "inferno", "cividis", "turbo"]
        )
        self._cmap_combo.currentTextChanged.connect(self._map_viewer.set_colormap)
        toolbar.addWidget(QLabel(" Colormap: "))
        toolbar.addWidget(self._cmap_combo)

        self._boundary_cb = QCheckBox("Boundaries")
        self._boundary_cb.toggled.connect(self._map_viewer.set_boundary_overlay)
        toolbar.addWidget(self._boundary_cb)

        toolbar.addSeparator()

        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self._reset)
        toolbar.addAction(reset_action)

        for i in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(i)), self)
            shortcut.activated.connect(
                lambda idx=i - 1: self._map_viewer.select_display_index(idx)
            )

    def _setup_statusbar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._file_label = QLabel("")
        self._status_bar.addWidget(self._file_label)
        self._pixel_label = QLabel("")
        self._status_bar.addWidget(self._pixel_label)
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
        self._or_panel.or_changed.connect(self._on_or_changed)
        self._map_viewer.pixel_hovered.connect(self._on_pixel_hover)
        self._map_viewer.pixel_clicked.connect(self._on_pixel_click)

        QTimer.singleShot(3000, self._check_updates)
        self._update_bar.open_url.connect(
            lambda url: QDesktopServices.openUrl(QUrl(url))
        )

    def _check_updates(self):
        self._update_checker = UpdateChecker()
        self._update_checker.update_available.connect(
            lambda info: self._update_bar.show_update(
                info.version, info.url, info.download_url
            )
        )
        self._update_checker.start()

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.appendPlainText(f"[{ts}] {msg}")

    def _on_or_changed(self, or_name: str):
        self._status_bar.showMessage(f"OR changed to: {or_name}")
        self._log(f"OR changed to: {or_name}")

    def _on_pixel_hover(self, x: int, y: int):
        if self._ebsd_map is None or self._ebsd_map.is_sparse:
            return
        rows, cols = self._ebsd_map.shape
        if not (0 <= y < rows and 0 <= x < cols):
            return
        flat = y * cols + x
        euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
        phi1, Phi, phi2 = euler[flat]
        pid = int(self._ebsd_map.phase_ids[flat])
        pname = (
            self._ebsd_map.phases[pid].name if pid < len(self._ebsd_map.phases) else "?"
        )
        bc_map = self._ebsd_map.band_contrast_map()
        iq = bc_map[y, x]
        self._status_bar.showMessage(
            f"x: {x}  y: {y} | Phase: {pname} | "
            f"\u03c6\u2081={phi1:.1f}\u00b0 \u03a6={Phi:.1f}\u00b0 \u03c6\u2082={phi2:.1f}\u00b0 | "
            f"IQ: {iq:.0f}"
        )

    def _on_pixel_click(self, x: int, y: int):
        if self._ebsd_map is None or self._ebsd_map.is_sparse:
            return
        rows, cols = self._ebsd_map.shape
        if not (0 <= y < rows and 0 <= x < cols):
            return
        flat = y * cols + x
        euler = self._ebsd_map.crystal_map.rotations.to_euler(degrees=True)
        phi1, Phi, phi2 = euler[flat]
        pid = int(self._ebsd_map.phase_ids[flat])
        pname = (
            self._ebsd_map.phases[pid].name if pid < len(self._ebsd_map.phases) else "?"
        )

        grain_id = -1
        grain = None
        if self._ebsd_map.grains:
            for g in self._ebsd_map.grains:
                if flat in g.pixel_indices:
                    grain_id = g.id
                    grain = g
                    break

        self._grain_labels["Grain ID"].setText(str(grain_id))
        self._grain_labels["Phase"].setText(pname)
        self._grain_labels["Area (px)"].setText(str(grain.area) if grain else "-")
        self._grain_labels["Eq. Diameter"].setText(
            f"{grain.equivalent_diameter:.1f}" if grain else "-"
        )
        self._grain_labels["Aspect Ratio"].setText(
            f"{grain.aspect_ratio:.2f}" if grain else "-"
        )
        self._grain_labels["Mean Orientation"].setText(
            f"({phi1:.1f}, {Phi:.1f}, {phi2:.1f})"
        )
        self._grain_labels["Neighbors"].setText(
            ", ".join(str(n) for n in grain.neighbor_ids)
            if grain and grain.neighbor_ids
            else "-"
        )

        if self._result is not None:
            parent_id = int(self._result.parent_grain_ids[flat])
            variant_id = int(self._result.variant_ids[flat])
            fit = float(self._result.fit_angles[flat])
            self._grain_labels["Parent Grain ID"].setText(str(parent_id))
            self._grain_labels["Variant ID"].setText(f"V{variant_id}")
            self._grain_labels["Fit Angle"].setText(f"{fit:.2f}\u00b0")
        else:
            for k in ("Parent Grain ID", "Variant ID", "Fit Angle"):
                self._grain_labels[k].setText("-")

        self._docks["Grain Info"].raise_()

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
            self._add_recent(path)
            self._map_viewer.set_ebsd_map(self._ebsd_map)
            self._phase_panel.set_phases(
                self._ebsd_map.phases, self._ebsd_map.phase_ids
            )
            n_pixels = self._ebsd_map.shape[0] * self._ebsd_map.shape[1]
            n_phases = len(self._ebsd_map.phases)
            self._file_label.setText(
                f"{path.name} | {self._ebsd_map.shape[0]}x{self._ebsd_map.shape[1]} "
                f"({n_pixels} px) | {n_phases} phase(s)"
            )
            msg = f"Loaded: {path.name} — {self._ebsd_map.shape[0]}x{self._ebsd_map.shape[1]} pixels"
            self._status_bar.showMessage(msg)
            self._log(msg)
        except Exception as e:
            self._status_bar.showMessage(f"Error loading file: {e}")
            self._log(f"ERROR loading file: {e}")

    def _run_reconstruction(self):
        if self._ebsd_map is None:
            self._status_bar.showMessage("No data loaded")
            return
        config = self._param_panel.get_config()
        or_config = self._or_panel.get_or_type()
        config_dict = config.model_dump()
        config_dict["or_type"] = or_config
        full_config = ReconstructionConfig(**config_dict)
        self._reconstruction_panel.start_reconstruction(self._ebsd_map, full_config)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._log(
            f"Reconstruction started — algorithm={full_config.algorithm}, OR={or_config}"
        )
        self._recon_start = datetime.now()

    def _on_reconstruction_done(self, result):
        self._progress_bar.setVisible(False)
        self._result = result
        if result is None:
            self._status_bar.showMessage("Reconstruction failed")
            self._log("Reconstruction FAILED")
            return
        self._map_viewer.set_reconstruction_result(result)
        self._stats_panel.update_stats(result, self._ebsd_map)
        n_parents = len(set(result.parent_grain_ids.tolist()))
        elapsed = (datetime.now() - self._recon_start).total_seconds()
        fit_valid = result.fit_angles[~np.isnan(result.fit_angles)]
        q = (
            np.percentile(fit_valid, [25, 50, 75, 90, 95])
            if len(fit_valid) > 0
            else [0] * 5
        )
        pct_recon = (
            np.sum(result.parent_grain_ids >= 0) / len(result.parent_grain_ids) * 100
        )
        summary = (
            f"Reconstruction complete — {n_parents} parent grains, "
            f"{pct_recon:.1f}% reconstructed in {elapsed:.1f}s"
        )
        self._status_bar.showMessage(summary)
        self._log(summary)
        self._log(
            f"  Fit quintiles: Q25={q[0]:.2f} Q50={q[1]:.2f} "
            f"Q75={q[2]:.2f} Q90={q[3]:.2f} Q95={q[4]:.2f}"
        )

    def _reset(self):
        self._ebsd_map = None
        self._result = None
        self._map_viewer.clear()
        self._status_bar.showMessage("Ready — Open an EBSD file to begin")
        self._log("Reset")

    def _save_file(self):
        if self._ebsd_map is None or self._result is None:
            self._status_bar.showMessage("No reconstruction result to save")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Reconstructed Data", "", "ANG Files (*.ang);;All Files (*)"
        )
        if not path:
            return
        try:
            from orix.quaternion import Rotation

            rot = Rotation(self._result.parent_orientations.reshape(-1, 4))
            parent_euler = rot.to_euler()
            cm = self._ebsd_map.crystal_map
            with open(path, "w") as f:
                f.write("# Reconstructed parent orientations\n")
                for i in range(cm.size):
                    x_val = cm.x[i] if cm.x is not None else 0
                    y_val = cm.y[i] if cm.y is not None else 0
                    f.write(
                        f"{parent_euler[i, 0]:.5f} {parent_euler[i, 1]:.5f} {parent_euler[i, 2]:.5f} "
                        f"{x_val:.5f} {y_val:.5f} 1.0 1.0 "
                        f"{int(self._result.parent_grain_ids[i])} 0 {self._result.fit_angles[i]:.4f}\n"
                    )
            self._log(f"Saved to {path}")
            self._status_bar.showMessage(f"Saved: {path}")
        except Exception as e:
            self._status_bar.showMessage(f"Save error: {e}")
            self._log(f"Save ERROR: {e}")

    def _export_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Image", "", "PNG (*.png);;SVG (*.svg);;All Files (*)"
        )
        if not path:
            return
        self._map_viewer.export_image(path)
        self._log(f"Exported image to {path}")

    def _export_stats(self):
        if self._result is None:
            self._status_bar.showMessage("No result to export")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Stats", "", "CSV (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            parent_ids = self._result.parent_grain_ids
            unique = np.unique(parent_ids[parent_ids >= 0])
            with open(path, "w") as f:
                f.write("parent_id,size_px,mean_fit\n")
                for pid in unique:
                    mask = parent_ids == pid
                    size = int(mask.sum())
                    mf = float(np.nanmean(self._result.fit_angles[mask]))
                    f.write(f"{pid},{size},{mf:.4f}\n")
            self._log(f"Exported stats to {path}")
        except Exception as e:
            self._log(f"Export stats ERROR: {e}")

    def _export_map_data(self):
        if self._ebsd_map is None:
            self._status_bar.showMessage("No data loaded")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Map Data", "", "NumPy (*.npy);;All Files (*)"
        )
        if not path:
            return
        try:
            mode = self._map_viewer.current_display_mode()
            data = self._ebsd_map.compute_map_property(mode)
            np.save(path, data)
            self._log(f"Exported '{mode}' to {path}")
        except Exception as e:
            self._log(f"Export data ERROR: {e}")

    # -- Recent files -------------------------------------------------------

    def _recent_paths(self) -> list[str]:
        return self._settings.value("recent_files", [], type=list)

    def _add_recent(self, path: Path):
        paths = self._recent_paths()
        s = str(path)
        if s in paths:
            paths.remove(s)
        paths.insert(0, s)
        self._settings.setValue("recent_files", paths[:_MAX_RECENT])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        paths = self._recent_paths()
        if not paths:
            action = self._recent_menu.addAction("(none)")
            action.setEnabled(False)
            return
        for p in paths:
            action = self._recent_menu.addAction(Path(p).name)
            action.setToolTip(p)
            action.triggered.connect(lambda checked, fp=p: self._load_file(Path(fp)))
        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("Clear Recent")
        clear_action.triggered.connect(self._clear_recent)

    def _clear_recent(self):
        self._settings.remove("recent_files")
        self._rebuild_recent_menu()

    # -- Window state -------------------------------------------------------

    def _restore_state(self):
        geo = self._settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)
        state = self._settings.value("window_state")
        if state:
            self.restoreState(state)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.is_file():
                self._load_file(path)

    def closeEvent(self, event):
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        super().closeEvent(event)
