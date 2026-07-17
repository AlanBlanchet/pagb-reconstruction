"""Construction smoke tests for the restyled widgets.

Guards the theme migration: every widget must build under a real QApplication,
survive a theme switch (SCSS recompile), and drive its icon/state paths.

Uses pytest-qt's ``qtbot``, which keeps each widget referenced and cleans it up
deterministically — without it, a widget GC'd mid-run trips pyqtgraph's
``WidgetGroup`` weakrefs and segfaults during a later PlotWidget construction.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _theme(qapp):
    from pagb_reconstruction.ui.theme import apply_theme

    apply_theme(qapp)


def test_all_widgets_construct(qtbot):
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer
    from pagb_reconstruction.ui.widgets.or_panel import ORPanel
    from pagb_reconstruction.ui.widgets.param_panel import ParamPanel
    from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatsDashboard
    from pagb_reconstruction.ui.widgets.update_bar import UpdateBar

    for cls in (MapViewer, ORPanel, ParamPanel, PoleFigureWidget,
                ReconstructionPanel, StatsDashboard, UpdateBar):
        w = cls()
        qtbot.addWidget(w)
        assert w is not None


def test_task_item_status_icons(qtbot):
    from pagb_reconstruction.ui.widgets.task_manager import TaskItem

    item = TaskItem("t1", "Reconstructing")
    qtbot.addWidget(item)
    for status in ("running", "done", "error", "cancelled"):
        item.set_status(status)
        assert not item._icon.pixmap().isNull(), status


def test_collapsible_card_toggles(qtbot):
    from pagb_reconstruction.ui.widgets.param_panel import CollapsibleCard

    card = CollapsibleCard("Grain Detection", "grain")
    qtbot.addWidget(card)
    assert card._expanded
    card.set_expanded(False)
    assert not card._expanded
    assert not card._chevron.pixmap().isNull()


def test_theme_switch_recompiles(qapp):
    from pagb_reconstruction.ui.theme import THEMES, active_theme, set_theme

    for name in THEMES:
        set_theme(name, qapp)
        assert active_theme().name == name
    set_theme("Carbon", qapp)


def test_prebuilt_widget_retheme_on_switch(qtbot, qapp):
    """A widget built under one theme must re-theme on a live switch.

    Guards the stale-inline-style bug: styling must live in the global SCSS
    (type/objectName selectors), not in construction-time setStyleSheet, so
    the global re-apply covers already-built widgets.
    """
    from PySide6.QtWidgets import QApplication

    from pagb_reconstruction.ui.theme import THEMES, set_theme
    from pagb_reconstruction.ui.widgets.stats_dashboard import StatCard

    set_theme("Carbon", qapp)
    card = StatCard("Parents", "42")
    qtbot.addWidget(card)
    # Inline construction-baked colours would survive the switch — the widget
    # itself must carry no palette-bearing stylesheet.
    assert "#" not in card.styleSheet(), "StatCard bakes palette colours inline"
    assert "#" not in card._value.styleSheet(), "StatCard value label bakes colours"

    set_theme("Latte", qapp)
    try:
        qss = QApplication.instance().styleSheet()
        assert "StatCard" in qss
        assert THEMES["Latte"].elevated.lower() in qss.lower()
        assert THEMES["Carbon"].elevated.lower() not in qss.lower()
    finally:
        set_theme("Carbon", qapp)
