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


def test_dock_tabs_actually_fit_their_bar(qtbot):
    """Every dock tab must FIT — not merely be flagged scrollable.

    Qt does not render scroll arrows for QMainWindow-tabified docks in this
    style, so an overflowing tab is simply unreachable: "Info" was cut to zero
    characters at the default 320px right dock. Asserting usesScrollButtons() was
    verifying a flag Qt then ignored; assert the geometry instead.
    """
    from PySide6.QtWidgets import QTabBar

    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1600, 1000)
    w.show()
    qtbot.waitExposed(w)
    # Dock areas are laid out over several passes; measure once settled.
    qtbot.wait(200)

    # Qt leaves stale tab bars behind after re-tabifying — several report
    # isVisible() at the same position with different tab sets. Group by tab set
    # and judge the real (widest) bar for each: if that one fits, the user can
    # reach every tab.
    widest: dict[tuple, QTabBar] = {}
    for bar in w.findChildren(QTabBar):
        if not bar.count() or not bar.isVisible():
            continue
        key = tuple(bar.tabText(i) for i in range(bar.count()))
        if key not in widest or bar.width() > widest[key].width():
            widest[key] = bar
    assert widest, "expected tabified docks"

    for labels, bar in widest.items():
        needed = sum(bar.tabSizeHint(i).width() for i in range(bar.count()))
        assert needed <= bar.width(), (
            f"tabs {list(labels)} need {needed}px in a {bar.width()}px bar — "
            f"{needed - bar.width()}px overflows and is unreachable, and Qt draws "
            "no scroll arrows for QMainWindow-tabified docks"
        )


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


def test_right_docks_are_not_width_capped(qtbot):
    """A user must be able to widen the right dock to read the OR histogram.

    A hard setMaximumWidth(380) against a 320 default leaves 60px of travel, so
    dragging the splitter reads as "nothing happens" — measured live as the root
    cause of the map using ~27% of its width while the docks sat 35-50% empty.
    The map keeps the dominant share via the resizeDocks default, not a cap that
    forbids the user from ever changing it.
    """
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    # Assert the property that matters — real splitter travel — not Qt's
    # sentinel, which differs between QWidget and QDockWidget.
    for name in ("Phases", "OR", "Params", "Info"):
        dock = w._docks[name]
        assert dock.maximumWidth() > 1000, (
            f"{name} dock is width-capped at {dock.maximumWidth()}px against a "
            "320px default, so the splitter has almost no travel and the OR "
            "histogram can never be given room"
        )


def test_dock_tabs_do_not_expand(qtbot):
    """Expanding tabs get squeezed to fit the bar, which is how labels shrank to
    nothing. With expanding off they keep their width and overflow to scroll."""
    from PySide6.QtWidgets import QTabBar

    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    for bar in w.findChildren(QTabBar):
        assert not bar.expanding(), "tab bar still squeezes its tabs"


def test_bottom_docks_cannot_squeeze_the_canvas(qtbot):
    """A later sizeHint (the stats/pole panels populating) grew the bottom dock
    after any re-assert, collapsing the canvas ~20% on a real window manager.
    A maximum height cannot be outvoted by a later layout pass."""
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.resize(1600, 1000)
    w._cap_bottom_docks()

    ceiling = max(200, int(w.height() * 0.42))
    for name in ("Reconstruction", "Statistics", "Poles", "Log"):
        dock = w._docks[name]
        assert dock.maximumHeight() <= ceiling, f"{name} can grow without bound"
    # the canvas therefore keeps at least ~58% of the window
    assert ceiling < w.height() * 0.5
