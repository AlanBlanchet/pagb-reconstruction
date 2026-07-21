"""Main window smoke guard — it must construct with the full toolbar/panel set."""


def test_main_window_constructs(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert w is not None


def test_reset_layout_restores_hidden_docks(qtbot):
    """Closing docks must never be unrecoverable.

    A user could hide the Reconstruction panel — the one that runs the analysis —
    and Qt persisted that state across every future launch, recoverable only via
    an undiscoverable View-menu checkbox.
    """
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    for name in ("Reconstruction", "Params", "Statistics"):
        w._docks[name].setVisible(False)
    assert w._docks["Reconstruction"].isHidden()

    w.reset_layout()

    # isHidden() is the right check: a tabified dock that is not the current tab
    # reports isVisible() False even though it is perfectly reachable.
    for name, dock in w._docks.items():
        assert not dock.isHidden(), f"{name} still closed after reset_layout"


def test_dock_tabs_overflow_instead_of_vanishing(qtbot):
    """Tabbed docks must scroll, not silently drop tabs under width pressure."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTabBar

    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    bars = w.findChildren(QTabBar)
    assert bars, "expected tabified docks"
    for bar in bars:
        assert bar.usesScrollButtons(), "tab bar drops tabs instead of scrolling"
        assert bar.elideMode() == Qt.TextElideMode.ElideRight


def test_viewport_adapts_to_map_aspect(qtbot):
    """Issue #11: "la fenetre de visualisation trop large et pas assez haute
    (pas adaptee a la cartographie chargee)"."""
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1400, 900)

    w._fit_layout_to_map_aspect(0.5)   # tall map -> canvas needs height
    tall = w._bottom_dock_height()
    w._fit_layout_to_map_aspect(3.0)   # wide map -> bottom docks may take more
    wide = w._bottom_dock_height()

    assert tall <= wide, f"tall map got more bottom-dock height ({tall}) than wide ({wide})"
    assert tall >= 140, "bottom docks must stay usable"


def test_reset_layout_action_is_reachable(qtbot):
    from PySide6.QtGui import QAction

    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    titles = [a.text().replace("&", "") for a in w.findChildren(QAction)]
    assert any("Reset Layout" in t for t in titles), "no Reset Layout action"
