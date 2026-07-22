import logging
import platform
import sys
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np
import orix
from PySide6 import __version__ as qt_version
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction import __version__
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.fit_metrics import reconstruction_quality
from pagb_reconstruction.utils.compute import Quaternions
from pagb_reconstruction.core.reconstruction import ReconstructionConfig
from pagb_reconstruction.core.updater import UpdateChecker
from pagb_reconstruction.utils import bug_report, logging_setup
from pagb_reconstruction.io.base import load_ebsd
from pagb_reconstruction.io.figure_export import export_map_figure
from pagb_reconstruction.io.reconstruction_export import ReconstructionExporter
from pagb_reconstruction.ui.theme import THEMES, active_theme, icon, set_theme
from pagb_reconstruction.ui.workspaces import PROFILES, apply_profile
from pagb_reconstruction.ui.widgets.map_viewer import MapViewer
from pagb_reconstruction.ui.widgets.or_panel import ORPanel
from pagb_reconstruction.ui.widgets.param_panel import ParamPanel
from pagb_reconstruction.ui.widgets.phase_panel import PhasePanel
from pagb_reconstruction.ui.widgets.misorientation_panel import MisorientationPanel
from pagb_reconstruction.ui.widgets.parent_review import ParentReviewPanel
from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget
from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel
from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard
from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel
from pagb_reconstruction.ui.widgets.task_manager import TaskManager
from pagb_reconstruction.ui.widgets.update_bar import UpdateBar
from pagb_reconstruction.ui.widgets.workflow_rail import WorkflowRail

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
        # Actions that can only fail with no map loaded; gated below.
        self._data_actions: list = []
        self.setAcceptDrops(True)
        self._setup_ui()
        self._restore_state()
        # Restoring a saved layout re-tabifies the docks, and Qt builds NEW tab
        # bars for it — so the setting has to be re-applied afterwards.
        self._make_dock_tabs_scrollable()
        if not self._settings.contains("window_geometry"):
            self.showMaximized()

    def _setup_ui(self):
        self.setWindowTitle("PAGB Reconstruction")
        self.setMinimumSize(1200, 800)

        self.setCorner(
            Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setCorner(
            Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea
        )

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self._update_bar = UpdateBar()
        central_layout.addWidget(self._update_bar)

        self._map_viewer = MapViewer()
        central_layout.addWidget(self._map_viewer, 1)
        self.setCentralWidget(central)

        self._task_manager = TaskManager(central)

        self._param_panel = ParamPanel()
        self._phase_panel = PhasePanel()
        self._or_panel = ORPanel()
        self._reconstruction_panel = ReconstructionPanel()
        self._stats_dashboard = StatsDashboard()
        self._summary_panel = SummaryPanel()
        self._pole_figure = PoleFigureWidget()
        self._parent_review = ParentReviewPanel()
        self._misorientation_panel = MisorientationPanel()

        self._grain_info = QWidget()
        self._grain_form = QFormLayout(self._grain_info)
        _hint = QLabel("Click a grain on the map to inspect it")
        _hint.setWordWrap(True)
        _hint.setObjectName("infoHint")
        self._grain_form.addRow(_hint)
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

        # NOT the binding constraint at max bottom-dock drag, despite two
        # attempts to tune it: the central row bottoms out at ~233px set by the
        # MAP viewer's own 159px minimum plus the update bar, and 233 already
        # exceeds any floor tried here. Raising 120 -> 160 changed max dock reach
        # by 3-5px and did nothing for the Params panel it was meant to help.
        # Kept low so it never becomes the constraint; Params being scrollable
        # when the user has deliberately maximised the bottom dock is inherent,
        # not a bug to tune away.
        right_min = (240, 120)
        bottom_min = (400, 80)

        # Right dock follows the analysis workflow, data first:
        # Phases (what's loaded) -> OR (relationship) -> Params (tuning) ->
        # Info (per-grain inspection).
        dock_phases = self._add_dock(
            "Phases",
            self._phase_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )
        dock_or = self._add_dock(
            "OR",
            self._or_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )
        dock_params = self._add_dock(
            "Params",
            self._param_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )
        _info_scroll = QScrollArea()
        _info_scroll.setWidgetResizable(True)
        _info_scroll.setFrameShape(QFrame.Shape.NoFrame)
        _info_scroll.setWidget(self._grain_info)
        dock_grain_info = self._add_dock(
            "Info",
            _info_scroll,
            Qt.DockWidgetArea.RightDockWidgetArea,
            right_min,
        )

        self.tabifyDockWidget(dock_phases, dock_or)
        self.tabifyDockWidget(dock_or, dock_params)
        self.tabifyDockWidget(dock_params, dock_grain_info)
        dock_phases.raise_()
        self._make_dock_tabs_scrollable()

        dock_recon = self._add_dock(
            "Reconstruction",
            self._reconstruction_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_stats = self._add_dock(
            "Statistics",
            self._stats_dashboard,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_pole = self._add_dock(
            "Poles",
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
        dock_summary = self._add_dock(
            "Summary",
            self._summary_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_misor = self._add_dock(
            "Misorientation",
            self._misorientation_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )
        dock_parents = self._add_dock(
            "Parents",
            self._parent_review,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            bottom_min,
        )

        self.tabifyDockWidget(dock_recon, dock_stats)
        self.tabifyDockWidget(dock_stats, dock_summary)
        self.tabifyDockWidget(dock_summary, dock_pole)
        self.tabifyDockWidget(dock_pole, dock_misor)
        self.tabifyDockWidget(dock_misor, dock_parents)
        self.tabifyDockWidget(dock_parents, dock_log)
        dock_recon.raise_()
        self._make_dock_tabs_scrollable()

        self._bottom_docks = [
            dock_recon, dock_stats, dock_summary, dock_pole, dock_misor,
            dock_parents, dock_log,
        ]
        self._right_dock = dock_params

        self._docks = {
            "Params": dock_params,
            "Phases": dock_phases,
            "OR": dock_or,
            "Info": dock_grain_info,
            "Reconstruction": dock_recon,
            "Statistics": dock_stats,
            "Poles": dock_pole,
            "Summary": dock_summary,
            "Misorientation": dock_misor,
            "Parents": dock_parents,
            "Log": dock_log,
        }

        # The map is the product, so the docks START compact and it gets the
        # dominant area. That default is a starting point, not a ceiling: a
        # setMaximumWidth cap here left only 60px of splitter travel, which reads
        # as "the splitter does nothing" and made it impossible to ever give the
        # OR histogram or the stats grid the room they need.
        self.resizeDocks([dock_phases], [320], Qt.Orientation.Horizontal)
        self.resizeDocks([dock_recon], [230], Qt.Orientation.Vertical)

        self._setup_workflow_rail()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        # Nothing is loaded yet, so anything needing data can only fail.
        self._set_data_actions_enabled(False)
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


    def _make_dock_tabs_scrollable(self):
        """Tabbed docks must overflow, not silently drop tabs.

        Under width pressure Qt was dropping whole tabs with no arrow or
        ellipsis, so panels disappeared outright — different ones at different
        widths.
        """
        from PySide6.QtWidgets import QTabBar

        for bar in self.findChildren(QTabBar):
            bar.setUsesScrollButtons(True)
            # Expanding tabs are squeezed to fit the bar; with it off they keep
            # their natural width, overflow, and the scroll arrows appear.
            bar.setExpanding(False)
            # ElideRight lets Qt shrink a tab label to zero characters, which is
            # how tabs "vanished". ElideNone forces it to keep the tab's width
            # and show scroll arrows instead.
            bar.setElideMode(Qt.TextElideMode.ElideNone)

    def reset_layout(self):
        """Restore every panel and the default arrangement.

        Closing docks was unrecoverable: a user could hide the Reconstruction
        panel — the one that runs the analysis — and Qt persisted that state
        across every future launch.
        """
        for dock in self._docks.values():
            dock.setVisible(True)
            dock.setFloating(False)
        # Derived from where the docks actually live, never a hand-written list:
        # the previous literal omitted Summary and Misorientation, so any dock
        # added later would be reset into its own stray tab strip. Same
        # hard-coded-name-list bug that made the Analyze profile hide those exact
        # docks.
        right = [n for n, d in self._docks.items()
                 if self.dockWidgetArea(d) == Qt.DockWidgetArea.RightDockWidgetArea]
        bottom = [n for n, d in self._docks.items()
                  if self.dockWidgetArea(d) == Qt.DockWidgetArea.BottomDockWidgetArea]
        for group in (right, bottom):
            names = [n for n in group if n in self._docks]
            for first, second in zip(names, names[1:]):
                self.tabifyDockWidget(self._docks[first], self._docks[second])
            if names:
                self._docks[names[0]].raise_()
        if "Phases" in self._docks:
            self.resizeDocks([self._docks["Phases"]], [320], Qt.Orientation.Horizontal)
        if "Reconstruction" in self._docks:
            self.resizeDocks(
                [self._docks["Reconstruction"]], [230], Qt.Orientation.Vertical
            )
        # The user asked for defaults back, so let map loads reshape again.
        self._layout_restored = False
        self._make_dock_tabs_scrollable()
        self._log("Layout reset")

    def _reassert_canvas_share(self):
        """Re-apply the canvas share after something resized the docks."""
        if self._ebsd_map is None:
            return
        rows, cols = self._ebsd_map.shape
        if rows:
            self._fit_layout_to_map_aspect(cols / rows)

    # Split presets (Map / Balanced / Panel) were built here and REMOVED after
    # live verification. They worked headless and in the test suite, but on the
    # real app only the GROW direction took effect: these docks are tabified, so
    # the group cannot shrink past the tallest tab's sizeHint (~383px, driven by
    # Poles ~555 and Statistics ~523), and pinning min/max around the resize did
    # not defeat that live even though it did offscreen — the third recurrence of
    # this headless/live divergence in this widget.
    #
    # A "Map" button that silently does nothing is the same defect class as the
    # dead controls this app was just cleaned of, and worse than no button: cold
    # launch already sits at the clamp, so the no-op is invisible. Re-attempting
    # this means first lowering the tallest tab's sizeHint, and verifying LIVE —
    # the offscreen suite cannot see this failure.

    def _set_data_actions_enabled(self, enabled: bool) -> None:
        """Gate the actions that need a loaded map.

        An enabled control that can only produce an error or an empty file is
        the same false affordance as a button that does nothing.
        """
        for action in self._data_actions:
            action.setEnabled(enabled)

    def _show_parent_info(self, parent_id: int) -> None:
        """Fill the Info panel from a Parents-table selection."""
        if self._result is None or parent_id < 0:
            return
        ids = np.asarray(self._result.parent_grain_ids)
        member = np.nonzero(ids == parent_id)[0]
        if member.size == 0:
            return
        idx = int(member[0])
        # Blank the fields that describe the last CHILD grain clicked on the map.
        # Left in place they sit beside the parent's numbers and read as though
        # they belong to it — a trust bug for anyone cross-referencing IDs.
        for field in ("Grain ID", "Phase", "Eq. Diameter", "Aspect Ratio",
                      "Neighbors", "Mean Orientation"):
            self._grain_labels[field].setText("-")
        self._grain_labels["Parent Grain ID"].setText(str(parent_id))
        variant = int(np.asarray(self._result.variant_ids)[idx])
        self._grain_labels["Variant ID"].setText(f"V{variant}" if variant >= 0 else "-")
        fits = np.asarray(self._result.fit_angles, dtype=float)[member]
        valid = fits[~np.isnan(fits)]
        self._grain_labels["Fit Angle"].setText(
            f"{float(np.mean(valid)):.2f}\u00b0" if valid.size else "-"
        )
        self._grain_labels["Area (px)"].setText(str(int(member.size)))

    def _bottom_dock_height(self) -> int:
        return self._docks["Reconstruction"].height()

    def _fit_layout_to_map_aspect(self, map_aspect: float):
        """Shape the layout for a newly loaded map — unless the user has a saved
        one. Restoring a layout and then resizing the docks on the next map load
        threw the restore away, which is why dock sizes looked like they never
        persisted; Qt was restoring them correctly and this method overwrote it.
        """
        if getattr(self, "_layout_restored", False):
            return
        self._fit_layout_to_map_aspect_inner(map_aspect)

    def _fit_layout_to_map_aspect_inner(self, map_aspect: float):
        """Shape the central area toward the loaded map's aspect ratio.

        A tall map inside a wide, short viewport wastes most of the canvas on
        empty background (issue #11: "trop large et pas assez haute, pas adaptée
        à la cartographie chargée"). Give the bottom docks less room for a tall
        map, more for a wide one, within sane bounds.
        """
        if map_aspect <= 0 or "Reconstruction" not in self._docks:
            return
        available = max(self.height() - 160, 300)
        if map_aspect < 1.0:
            frac = 0.16
        elif map_aspect < 2.0:
            frac = 0.24
        else:
            frac = 0.32
        target = max(140, min(int(available * frac), int(available * 0.4)))
        self.resizeDocks(
            [self._docks["Reconstruction"]], [target], Qt.Orientation.Vertical
        )
        self._cap_bottom_docks()

    def _cap_bottom_docks(self):
        """Hard ceiling on the bottom docks' height.

        Re-asserting the size after a resize is timing-dependent: populating the
        statistics and pole panels grows the dock again on a later layout pass,
        which is why the canvas still collapsed ~20% on a real window manager
        even though it measured stable headless. A maximum height cannot be
        outvoted by a later sizeHint, so the canvas can never be squeezed below
        its share — while leaving the user free to resize within that range.
        """
        # Bound by what the MAP needs, not by an arbitrary fraction. The central
        # widget's own minimum is ~159px, so the previous 0.42-of-window cap was
        # never protecting the map — it only forbade the user from growing a
        # data-dense tab (Summary's results line clipped at maximum drag while
        # the map sat at 637px). Reserve a genuinely readable map instead and let
        # the user have the rest; the DEFAULT height stays map-dominant.
        # This is a SAFETY cap, not the operative limit. Qt's own layout binds
        # first: the bottom docks span the full width (both bottom corners are
        # assigned to them), so the central row's floor is the RIGHT dock's
        # minimum height, not the map's — measured, asking for 900px of dock
        # yields 645. The cap exists only to stop a later sizeHint from letting
        # the docks swallow the canvas; the previous 0.42-of-window value was
        # tighter than Qt's limit and so became the thing blocking the user.
        _MAP_FLOOR = 220
        ceiling = max(200, self.height() - _MAP_FLOOR)
        # Derived from the dock list, never a hand-written name set: a new bottom
        # dock would otherwise be left uncapped and the group sizes to it.
        for dock in self._bottom_docks:
            dock.setMaximumHeight(ceiling)

    def _reveal_docks_added_since(self, known_names) -> None:
        """Show docks that did not exist when this layout was saved.

        restoreState() only positions docks its blob knows about, so a dock
        shipped in a later release stays hidden forever and the View menu is the
        only way back \u2014 which no first-time-after-upgrade user finds.
        """
        if not known_names:
            return
        known = set(known_names)
        added = [
            dock for name, dock in self._docks.items()
            if name not in known and dock.isHidden()
        ]
        for dock in added:
            area = self.dockWidgetArea(dock)
            sibling = next(
                (
                    d for nm, d in self._docks.items()
                    if nm in known and not d.isHidden()
                    and self.dockWidgetArea(d) == area
                ),
                None,
            )
            if sibling is not None:
                self.tabifyDockWidget(sibling, dock)
            dock.show()
        if added:
            self._make_dock_tabs_scrollable()

    def _setup_workflow_rail(self):
        """The analysis order, visible and clickable, on the left edge.

        Tab order was the only hint of what to do first. Each stage surfaces the
        panels it needs; the map never moves. Additive — every tab keeps
        working, so the routing is verifiable stage by stage.
        """
        self._workflow_rail = WorkflowRail()
        self._workflow_rail.stage_selected.connect(self._on_workflow_stage)
        self._sync_rail_to_docks()
        rail_bar = QToolBar("Workflow")
        rail_bar.setObjectName("workflowRailBar")
        rail_bar.setMovable(False)
        rail_bar.addWidget(self._workflow_rail)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, rail_bar)

    # stage -> (right dock to raise, bottom dock to raise)
    _STAGE_PANELS = {
        "phases": ("Phases", None),
        "or": ("OR", "Misorientation"),
        "params": ("Params", None),
        "run": (None, "Reconstruction"),
        "review": ("Info", "Parents"),
    }

    # dock name -> the stage it belongs to; docks absent here have no stage and
    # CLEAR the rail cue (saying nothing beats claiming a wrong stage).
    _DOCK_STAGE = {
        "Phases": "phases",
        "OR": "or",
        "Misorientation": "or",
        "Params": "params",
        "Reconstruction": "run",
        "Parents": "review",
        "Info": "review",
    }

    def _sync_rail_to_docks(self) -> None:
        """Keep the rail's cue truthful when the user navigates by tab."""
        for name, dock in self._docks.items():
            dock.visibilityChanged.connect(
                lambda visible, n=name: self._on_dock_surfaced(n) if visible else None
            )

    def _on_dock_surfaced(self, name: str) -> None:
        self._workflow_rail.set_current(self._DOCK_STAGE.get(name))

    def _on_workflow_stage(self, key: str) -> None:
        if key != "load":
            self._stage_before_load = key
        if key == "load":
            # "Load" is an ACTION, not a destination: run the picker, then put
            # the cue back where the user actually is. Leaving it current forever
            # was measured as a stale "you are here" (11th-pass verdict).
            previous = getattr(self, "_stage_before_load", None)
            self._open_file()
            self._workflow_rail.set_current(previous)
            return
        right, bottom = self._STAGE_PANELS.get(key, (None, None))
        for name in (right, bottom):
            if name is None:
                continue
            dock = self._docks.get(name)
            if dock is not None:
                dock.show()
                dock.raise_()

    def _setup_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setIcon(icon("open"))
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save...", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setIcon(icon("save"))
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)
        self._data_actions.append(save_action)

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

        view_menu.addSeparator()
        view_menu.addSeparator()
        _reset_layout_menu = QAction("Reset &Layout", self)
        _reset_layout_menu.setToolTip("Restore all panels and the default arrangement")
        _reset_layout_menu.triggered.connect(self.reset_layout)
        view_menu.addAction(_reset_layout_menu)

        view_menu.addSeparator()
        workspace_menu = view_menu.addMenu("Workspace")
        workspace_menu.setIcon(icon("layers"))
        for i, prof in enumerate(PROFILES.values(), start=1):
            act = workspace_menu.addAction(icon(prof.icon), prof.name)
            act.setShortcut(QKeySequence(f"Ctrl+{i}"))
            act.triggered.connect(
                lambda checked=False, p=prof: apply_profile(self, p)
            )

        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Theme")
        for theme_name in THEMES:
            action = theme_menu.addAction(theme_name)
            action.triggered.connect(
                lambda checked, n=theme_name: self._switch_theme(n)
            )

        tools_menu = menu_bar.addMenu("&Tools")
        export_img = QAction("Export Image (PNG/SVG)...", self)
        export_img.setIcon(icon("export_image"))
        export_img.triggered.connect(self._export_image)
        tools_menu.addAction(export_img)
        self._data_actions.append(export_img)

        export_stats = QAction("Export Stats (CSV)...", self)
        export_stats.setIcon(icon("export_data"))
        export_stats.triggered.connect(self._export_stats)
        tools_menu.addAction(export_stats)

        export_data = QAction("Export Map Data...", self)
        self._data_actions.append(export_data)
        export_data.setIcon(icon("export_data"))
        export_data.triggered.connect(self._export_map_data)
        tools_menu.addAction(export_data)

        help_menu = menu_bar.addMenu("&Help")
        bug_action = QAction("Report &Bug...", self)
        bug_action.setIcon(icon("bug"))
        bug_action.triggered.connect(self._report_bug)
        help_menu.addAction(bug_action)

        log_action = QAction("Open &Log File", self)
        log_action.triggered.connect(self._open_log_file)
        help_menu.addAction(log_action)
        help_menu.addSeparator()
        about_action = QAction("&About", self)
        about_action.setIcon(icon("about"))
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")
        # Label every action: icon-only left Run as an unidentifiable play glyph
        # and made Zoom/Export icons ambiguous.
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        open_action = QAction(icon("open"), "Open", self)
        open_action.setToolTip("Open EBSD file (Ctrl+O)")
        open_action.triggered.connect(self._open_file)
        toolbar.addAction(open_action)

        save_action = QAction(icon("save"), "Save", self)
        save_action.setToolTip("Save reconstruction data")
        save_action.triggered.connect(self._save_file)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        run_action = QAction(icon("run"), "Run", self)
        run_action.setToolTip("Run reconstruction (Ctrl+R)")
        run_action.setShortcut(QKeySequence("Ctrl+R"))
        run_action.triggered.connect(self._run_reconstruction)
        toolbar.addAction(run_action)

        self._stop_action = QAction(icon("stop"), "Stop", self)
        self._stop_action.setToolTip("Stop reconstruction (Esc)")
        self._stop_action.setShortcut(QKeySequence("Escape"))
        self._stop_action.triggered.connect(self._reconstruction_panel._cancel)
        # Escape is an app-wide shortcut and a reflex key; keep it inert unless
        # a run is in flight, or a stray press fires Stop against whatever the
        # app is doing (observed live as a silent result reset).
        self._stop_action.setEnabled(False)
        toolbar.addAction(self._stop_action)

        toolbar.addSeparator()

        zoom_in = QAction(icon("zoom_in"), "Zoom In", self)
        zoom_in.setToolTip("Zoom in")
        zoom_in.triggered.connect(lambda: self._map_viewer.zoom(1.25))
        toolbar.addAction(zoom_in)

        zoom_out = QAction(icon("zoom_out"), "Zoom Out", self)
        zoom_out.setToolTip("Zoom out")
        zoom_out.triggered.connect(lambda: self._map_viewer.zoom(0.8))
        toolbar.addAction(zoom_out)

        zoom_fit = QAction(icon("fit"), "Fit", self)
        zoom_fit.setToolTip("Fit map to view")
        zoom_fit.triggered.connect(self._map_viewer.zoom_fit)
        toolbar.addAction(zoom_fit)

        toolbar.addSeparator()

        export_img = QAction(icon("export_image"), "Export Image", self)
        export_img.setToolTip("Export current view as image")
        export_img.triggered.connect(self._export_image)
        toolbar.addAction(export_img)

        export_data = QAction(icon("export_data"), "Export Data", self)
        export_data.setToolTip("Export map data to file")
        export_data.triggered.connect(self._export_map_data)
        toolbar.addAction(export_data)

        view_toolbar = QToolBar("View")
        view_toolbar.setObjectName("view_toolbar")
        view_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBarBreak()
        self.addToolBar(view_toolbar)
        self._view_toolbar = view_toolbar
        toolbar = view_toolbar  # remaining view/display controls on the second row

        self._map_viewer._display_combo.setToolTip("Display mode")
        toolbar.addWidget(self._map_viewer._display_combo)
        self._map_viewer._hist_eq_cb.setToolTip("Apply histogram equalization")
        toolbar.addWidget(self._map_viewer._hist_eq_cb)

        toolbar.addSeparator()

        self._cmap_combo = QComboBox()
        self._cmap_combo.setToolTip("Colormap")
        self._cmap_combo.addItems(
            ["viridis", "plasma", "magma", "inferno", "cividis", "turbo"]
        )
        self._cmap_combo.currentTextChanged.connect(self._map_viewer.set_colormap)
        toolbar.addWidget(self._cmap_combo)

        self._boundary_cb = QCheckBox("Boundaries")
        self._boundary_cb.setToolTip("Show child grain boundary overlay")
        self._boundary_cb.toggled.connect(self._map_viewer.set_boundary_overlay)
        toolbar.addWidget(self._boundary_cb)

        self._parent_boundary_cb = QCheckBox("Parent boundaries")
        self._parent_boundary_cb.setToolTip(
            "Overlay reconstructed prior-austenite grain boundaries on the map"
        )
        self._parent_boundary_cb.toggled.connect(
            self._map_viewer.set_parent_boundary_overlay
        )
        toolbar.addWidget(self._parent_boundary_cb)
        # The viewer turns this on automatically when a reconstruction finishes;
        # keep the checkbox in step so it reflects the live overlay.
        self._map_viewer.parent_boundary_changed.connect(
            self._parent_boundary_cb.setChecked
        )

        toolbar.addSeparator()

        split_action = QAction(icon("split"), "Split", self)
        split_action.setToolTip("Toggle split view for comparison")
        split_action.setCheckable(True)
        split_action.toggled.connect(self._toggle_split)
        toolbar.addAction(split_action)

        self._map_viewer._split_combo.setToolTip("Split display mode")
        self._map_viewer._split_combo.setVisible(False)
        toolbar.addWidget(self._map_viewer._split_combo)

        line_action = QAction(icon("line_profile"), "Line Profile", self)
        line_action.setToolTip("Draw a misorientation line profile on the map (L)")
        line_action.setCheckable(True)
        line_action.setShortcut(QKeySequence("L"))
        line_action.toggled.connect(self._map_viewer.toggle_line_mode)
        # The viewer disarms itself once a profile completes; keep the button
        # in step so it never shows pressed for a mode that has ended.
        self._map_viewer.line_mode_changed.connect(line_action.setChecked)
        toolbar.addAction(line_action)

        roi_action = QAction(icon("roi"), "ROI", self)
        roi_action.setToolTip("Draw region of interest")
        roi_action.setCheckable(True)
        roi_action.toggled.connect(self._toggle_roi)
        toolbar.addAction(roi_action)

        clear_roi_action = QAction(icon("clear_roi"), "Clear ROI", self)
        clear_roi_action.setToolTip("Clear current ROI selection")
        clear_roi_action.triggered.connect(self._clear_roi)
        toolbar.addAction(clear_roi_action)

        fps_action = QAction("FPS", self)
        fps_action.setToolTip("Show a frames-per-second counter on the map")
        fps_action.setCheckable(True)
        fps_action.toggled.connect(self._map_viewer.set_fps_visible)
        toolbar.addAction(fps_action)

        toolbar.addSeparator()

        reset_action = QAction(icon("reset"), "Reset", self)
        reset_action.setToolTip("Reset all views and selections")
        reset_action.triggered.connect(self._reset)

        reset_layout_action = QAction(icon("reset_layout"), "Reset Layout", self)
        reset_layout_action.setToolTip("Restore all panels and the default arrangement")
        reset_layout_action.triggered.connect(self.reset_layout)
        toolbar.addAction(reset_layout_action)
        toolbar.addAction(reset_action)
        # Icon-only toolbars make an action hard to find; also expose it by NAME.
        self._reset_layout_action = reset_layout_action

        for i in range(1, 10):
            shortcut = QShortcut(QKeySequence(str(i)), self)
            shortcut.activated.connect(
                lambda idx=i - 1: self._map_viewer.select_display_index(idx)
            )

    def _setup_statusbar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._file_label = QLabel("")
        self._status_bar.addWidget(self._file_label, 1)
        self._pixel_label = QLabel("")
        self._status_bar.addWidget(self._pixel_label, 1)
        self._perf_label = QLabel("")
        self._status_bar.addPermanentWidget(self._perf_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("Ready — Open an EBSD file to begin")

    def _connect_signals(self):
        self._reconstruction_panel.run_requested.connect(self._run_reconstruction)
        self._reconstruction_panel.compare_requested.connect(self._open_compare)
        self._reconstruction_panel.reconstruction_finished.connect(
            self._on_reconstruction_done
        )
        self._or_panel.or_changed.connect(self._on_or_changed)
        self._map_viewer.pixel_clicked.connect(self._on_pixel_click)
        self._map_viewer.roi_changed.connect(self._on_roi_changed)

        self._parent_review.parent_selected.connect(self._map_viewer.highlight_parent)
        # Locating the grain without its numbers is two actions for one intent
        # \u2014 and the second asks the user to click a grain just described
        # as hard to see.
        self._parent_review.parent_selected.connect(self._show_parent_info)
        self._parent_review.reassign_requested.connect(self._on_reassign_parent)

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

    def _on_reassign_parent(self, source_id: int, target_id: int):
        """Reattach one parent to another and refresh everything from the result."""
        if self._result is None:
            return
        from pagb_reconstruction.core.manual_edit import reassign_parent

        try:
            updated = reassign_parent(self._result, source_id, target_id)
        except ValueError as e:
            self._status_bar.showMessage(f"Cannot reattach: {e}")
            self._log(f"Reattach parent {source_id} -> {target_id} failed: {e}")
            return
        self._result = updated
        self._map_viewer.set_reconstruction_result(updated)
        self._parent_review.set_result(updated)
        self._log(f"Reattached parent {source_id} to {target_id}")
        self._status_bar.showMessage(f"Parent {source_id} reattached to {target_id}")

    def _log(self, msg: str, highlight: bool = False):
        ts = datetime.now().strftime("%H:%M:%S")
        if highlight:
            # A one-time confirmation of a user action must not blend into
            # routine INFO lines on scrollback.
            self._log_text.appendHtml(
                f'<span style="color: {active_theme().accent};">[{ts}] {escape(msg)}</span>'
            )
        else:
            self._log_text.appendPlainText(f"[{ts}] {msg}")
        # Mirror into the session log file so a bug report carries it.
        logging.getLogger("pagb_reconstruction.ui").info("%s", msg)

    def _on_or_changed(self, or_name: str):
        self._status_bar.showMessage(f"OR changed to: {or_name}")
        self._log(f"OR changed to: {or_name}")
        # The chart compares the measured spectrum against THIS OR's peaks, so it
        # is wrong the moment the selection changes.
        self._misorientation_panel.set_or_type(or_name)

    def _on_roi_changed(self, x, y, w, h):
        self._status_bar.showMessage(f"ROI: ({x}, {y}) {w}\u00d7{h} px")

    def _on_pixel_click(self, x: int, y: int):
        if self._ebsd_map is None:
            return
        rows, cols = self._ebsd_map.shape
        if not (0 <= y < rows and 0 <= x < cols):
            return
        flat = self._ebsd_map.pixel_index_at(y, x)
        if flat < 0:
            return
        phi1, Phi, phi2 = self._ebsd_map.pixel_euler(flat)
        pid = int(self._ebsd_map.phase_ids[flat])
        pname = self._ebsd_map.phase_name(pid)

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
            if parent_id >= 0:
                self._map_viewer.highlight_parent(parent_id)
                if self._ebsd_map.grains:
                    parent_mask = self._result.parent_grain_ids == parent_id
                    child_ids = {
                        g.id
                        for g in self._ebsd_map.grains
                        if any(parent_mask[px] for px in g.pixel_indices)
                    }
                    n_children = len(child_ids)
                    self._status_bar.showMessage(
                        f"Parent #{parent_id} contains {n_children} child grain(s)"
                    )
            else:
                self._map_viewer.clear_highlight()
        else:
            for k in ("Parent Grain ID", "Variant ID", "Fit Angle"):
                self._grain_labels[k].setText("-")
            self._map_viewer.clear_highlight()
        # Info dock updates in place; do NOT force-raise it on every click — that
        # stole focus and trapped the user on the Info tab (and used a wrong key).

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
            self._set_data_actions_enabled(True)
            # Shape the canvas toward this map's aspect (issue #11).
            rows, cols = self._ebsd_map.shape
            if rows:
                self._fit_layout_to_map_aspect(cols / rows)
            self._misorientation_panel.set_ebsd_map(self._ebsd_map)
            self._misorientation_panel.set_or_type(self._or_panel.get_or_type())
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
        for d in self._bottom_docks:
            d.show()
        self._docks["Reconstruction"].raise_()
        config = self._param_panel.get_config()
        or_config = self._or_panel.get_or_type()
        config_dict = config.model_dump()
        config_dict["or_type"] = or_config
        full_config = ReconstructionConfig(**config_dict)
        self._reconstruction_panel.start_reconstruction(self._ebsd_map, full_config)
        self._stop_action.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._task_manager.submit("reconstruction", "Reconstruction")
        self._log(
            f"Reconstruction started — algorithm={full_config.algorithm}, OR={or_config}"
        )
        self._recon_start = datetime.now()

    def _open_compare(self):
        if self._ebsd_map is None:
            self._status_bar.showMessage("No data loaded")
            return
        from pagb_reconstruction.ui.widgets.compare_dialog import CompareDialog

        dlg = CompareDialog(self._ebsd_map, self._param_panel.get_config(), self)
        dlg.run_chosen.connect(self._on_compare_chosen)
        dlg.exec()

    def _on_compare_chosen(self, run):
        # Adopt the winning parameters; if the comparison ran on the full map its
        # result is directly usable, otherwise the user re-runs on the full map.
        self._param_panel.set_config(run.config)
        if run.result.parent_grain_ids.size == self._ebsd_map.crystal_map.size:
            self._recon_start = datetime.now()
            self._on_reconstruction_done(run.result)
            self._log(f"Compare: applied result of '{run.name}'")
        else:
            self._status_bar.showMessage(
                f"Parameters of '{run.name}' applied — press Run for the full map"
            )
            self._log(f"Compare: adopted parameters of '{run.name}' (preview crop)")

    def _on_reconstruction_done(self, result):
        if result is not None:
            apply_profile(self, PROFILES["Analyze"])
            self._make_dock_tabs_scrollable()
            # Populating the stats/pole panels grows the bottom dock AGAIN after
            # this returns, so re-assert once the event loop has settled.
            QTimer.singleShot(0, self._reassert_canvas_share)
            QTimer.singleShot(250, self._reassert_canvas_share)
            # The profile resizes the docks; re-assert the canvas share or the
            # map collapses exactly when the user most wants to see it.
            if self._ebsd_map is not None:
                rows, cols = self._ebsd_map.shape
                if rows:
                    self._fit_layout_to_map_aspect(cols / rows)
        self._progress_bar.setVisible(False)
        self._stop_action.setEnabled(False)
        if result is None:
            # Keep the previous result: it feeds Poles, Parents and export, and
            # overwriting it with None wipes them all with no undo.
            kept = " \u2014 previous result kept" if self._result is not None else ""
            self._status_bar.showMessage(f"Reconstruction failed{kept}")
            self._task_manager.complete("reconstruction", "error")
            self._log(f"Reconstruction FAILED{kept}")
            return
        self._result = result
        elapsed = (datetime.now() - self._recon_start).total_seconds()
        self._task_manager.complete("reconstruction", "done")
        self._map_viewer.set_reconstruction_result(result)
        self._parent_review.set_result(result)
        self._stats_dashboard.update_stats(result, self._ebsd_map, elapsed=elapsed)
        self._summary_panel.update_stats(result, self._ebsd_map, elapsed=elapsed)
        if result.optimized_or is not None:
            self._or_panel.set_optimized_or(result.optimized_or)
        self._pole_figure.set_orientations(result.parent_orientations)
        # Multi-metric fit readout (Taylor et al. 2024): area-weighted parent size
        # is the headline "closeness to reality" number, alongside % reconstructed
        # and the OR fit-angle distribution. Lets the user vary params for best fit.
        qual = reconstruction_quality(result, self._ebsd_map.step_size)
        summary = (
            f"Reconstruction complete — {qual.n_parents} parent grains, "
            f"{qual.pct_reconstructed:.1f}% reconstructed in {elapsed:.1f}s, "
            f"parent size {qual.area_weighted_ecd_um:.1f} µm area-weighted "
            f"(median {qual.median_ecd_um:.1f}), mean fit {qual.mean_fit_deg:.2f}°"
        )
        self._status_bar.showMessage(summary)
        self._perf_label.setText(f"{elapsed:.1f}s")
        self._log(summary)
        self._log(
            f"  Fit angle: median {qual.median_fit_deg:.2f}° "
            f"(Q25 {qual.fit_q25_deg:.2f}, Q75 {qual.fit_q75_deg:.2f}, "
            f"Q95 {qual.fit_q95_deg:.2f}°) — lower is closer to the ideal OR"
        )

    def _toggle_split(self, checked: bool):
        self._map_viewer.set_split_visible(checked)

    def _toggle_roi(self, checked: bool):
        if checked:
            if not self._map_viewer._roi_active:
                self._map_viewer.toggle_roi_mode()
        else:
            if self._map_viewer._roi_active:
                self._map_viewer.toggle_roi_mode()

    def _clear_roi(self):
        self._map_viewer.clear_roi()

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
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Save Reconstructed Data",
            "",
            "NumPy archive (*.npz);;ANG Files (*.ang);;All Files (*)",
        )
        if not path:
            return
        out = Path(path)
        if not out.suffix:
            out = out.with_suffix(".npz" if "npz" in selected else ".ang")
        try:
            ReconstructionExporter.save(out, self._ebsd_map, self._result)
            self._log(f"Saved to {out}")
            self._status_bar.showMessage(f"Saved: {out}")
        except Exception as e:
            self._status_bar.showMessage(f"Save error: {e}")
            self._log(f"Save ERROR: {e}")

    def _export_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Image",
            "",
            "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg);;All Files (*)",
        )
        if not path:
            return
        image = self._map_viewer.current_image()
        if image is None or self._ebsd_map is None:
            # Nothing computed yet — fall back to a raw widget grab.
            self._map_viewer.export_image(path)
            self._log(f"Exported image to {path}")
            return

        mode = self._map_viewer.current_display_mode()
        meta = self._map_viewer.current_meta()
        try:
            export_map_figure(
                path,
                image,
                title=mode,
                step_size=self._ebsd_map.step_size,
                unit=(meta.unit if meta else "") or "",
                colormap=(meta.colormap if meta and meta.colormap else "viridis"),
                categorical=bool(meta and meta.dtype == "discrete"),
                parent_segments=self._map_viewer.current_parent_segments(),
            )
            self._log(f"Exported figure (scale bar + key) to {path}")
        except Exception as e:  # noqa: BLE001 — never lose the user's export
            logging.getLogger(__name__).exception("Figure export failed")
            self._map_viewer.export_image(path)
            self._log(f"Exported image to {path} (plain: {e})")

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
        else:
            # Size to the real screen: showMaximized() relies on a window
            # manager, absent in sandboxes/CI, and silently leaves the
            # 1200x800 minimum.
            screen = QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.availableGeometry())
        state = self._settings.value("window_state")
        if state:
            self.restoreState(state)
            self._reveal_docks_added_since(self._settings.value("dock_names"))
            # A pre-two-row saved state re-docks both toolbars onto one
            # row; re-assert the break so the view toolbar keeps its row.
            self.insertToolBarBreak(self._view_toolbar)
            # The user has a layout of their own; do not reshape it on map load.
            self._layout_restored = True
        else:
            self._should_hide_bottom = True

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_should_hide_bottom", False):
            self._should_hide_bottom = False
            for d in self._bottom_docks:
                d.hide()
            self.resizeDocks([self._right_dock], [400], Qt.Orientation.Horizontal)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.is_file():
                self._load_file(path)

    def _switch_theme(self, name: str):
        app = QApplication.instance()
        if app:
            set_theme(name, app)
            self._log(f"Theme changed to: {name}")

    def _report_bug(self):
        body = (
            "**Describe the bug**\n"
            "<!-- A clear and concise description of what the bug is -->\n"
            "\n\n"
            "**Steps to reproduce**\n"
            "1. \n"
            "2. \n"
            "3. \n"
            "\n"
            "**Expected behavior**\n"
            "\n\n"
            "---\n"
            "**Environment**\n"
            f"- App: {__version__}\n"
            f"- Python: {sys.version}\n"
            f"- Platform: {platform.platform()}\n"
            f"- Qt: {qt_version}\n"
            f"- orix: {orix.__version__}\n"
            f"- numpy: {np.__version__}\n"
            f"- Compute: {Quaternions.__name__} ({getattr(Quaternions, 'device', '?')})\n"
            "\n**Recent log**\n"
            "```\n{log}\n```\n"
        )
        link = bug_report.issue_url(
            "https://github.com/AlanBlanchet/pagb-reconstruction/issues/new",
            body,
            logging_setup.tail(60),
        )
        QDesktopServices.openUrl(QUrl(link.url))
        # The browser may open behind the app window — without feedback the
        # click reads as dead.
        msg = "Bug report opened in your browser"
        if link.truncated:
            msg += " — log trimmed to fit; Help > Open Log File has the full one"
        self.statusBar().showMessage(msg, 8000)
        self._log(msg, highlight=True)

    def _open_log_file(self):
        """Reveal the session log so the user can attach it to a report."""
        path = logging_setup.log_file_path()
        logging_setup.flush()
        target = path if path.exists() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _show_about(self):
        QMessageBox.about(
            self,
            "About PAGB Reconstruction",
            f"<h3>PAGB Reconstruction v{__version__}</h3>"
            "<p>Prior Austenite Grain Boundary reconstruction from EBSD data.</p>"
            '<p><a href="https://github.com/AlanBlanchet/pagb-reconstruction">'
            "GitHub</a></p>",
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        central = self.centralWidget()
        if central and hasattr(self, "_task_manager"):
            self._task_manager.reposition(central.width(), central.height())
        # The ceiling is a fraction of window height, so it is stale the moment
        # the window changes size. Recomputing it only on map load froze the dock
        # at its load-time height. The dock deliberately does NOT auto-grow: every
        # scheme that made it do so destroyed a manual splitter drag, which is
        # worse than not growing.
        if hasattr(self, "_bottom_docks"):
            self._cap_bottom_docks()


    def closeEvent(self, event):
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        # Record which docks this layout knows about, so a later release can
        # tell its new docks apart from ones the user deliberately closed.
        self._settings.setValue("dock_names", sorted(self._docks))
        super().closeEvent(event)
