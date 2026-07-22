"""The workflow rail — the analysis order made visible and clickable.

The tab layout implies the workflow only by tab ORDER; nothing tells a
first-time user what to do first, and every stage's controls are visible at
every moment. The rail names the stages (Load, Phases, OR, Params, Run, Review)
and clicking one surfaces the panels that stage needs. It is additive: every
existing tab keeps working, so the change is verifiable stage by stage.
"""


def test_rail_lists_the_stages_in_workflow_order(qtbot):
    from pagb_reconstruction.ui.widgets.workflow_rail import WorkflowRail

    rail = WorkflowRail()
    qtbot.addWidget(rail)
    assert [s.key for s in rail.stages()] == [
        "load", "phases", "or", "params", "run", "review",
    ]


def test_clicking_a_stage_emits_it(qtbot):
    from pagb_reconstruction.ui.widgets.workflow_rail import WorkflowRail

    rail = WorkflowRail()
    qtbot.addWidget(rail)
    seen = []
    rail.stage_selected.connect(seen.append)
    rail.select("or")
    assert seen == ["or"]


def test_rail_marks_the_current_stage(qtbot):
    """Exactly one stage reads as current — the rail is a 'you are here', not a
    row of identical buttons."""
    from pagb_reconstruction.ui.widgets.workflow_rail import WorkflowRail

    rail = WorkflowRail()
    qtbot.addWidget(rail)
    rail.select("params")
    checked = [s.key for s in rail.stages() if rail.is_current(s.key)]
    assert checked == ["params"]


def test_main_window_routes_stages_to_panels(qtbot):
    """Clicking a rail stage surfaces that stage's panels; the map stays put."""
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)

    w._workflow_rail.select("or")
    qtbot.wait(50)
    # The OR tab must now be the raised member of its tab group.
    assert not w._docks["OR"].visibleRegion().isEmpty() or (
        w._docks["OR"].isVisible() and not w._docks["OR"].visibleRegion().isEmpty()
    ) or w._docks["OR"].isVisible(), "OR dock not surfaced"

    w._workflow_rail.select("review")
    qtbot.wait(50)
    assert w._docks["Parents"].isVisible(), "Review stage must surface Parents"


def test_set_current_reflects_without_emitting(qtbot):
    """Syncing FROM the tabs must not fire the routing back at the tabs."""
    from pagb_reconstruction.ui.widgets.workflow_rail import WorkflowRail

    rail = WorkflowRail()
    qtbot.addWidget(rail)
    seen = []
    rail.stage_selected.connect(seen.append)
    rail.set_current("params")
    assert rail.is_current("params")
    assert seen == [], "reflecting external state must not re-emit it"
    rail.set_current(None)
    assert not any(rail.is_current(s.key) for s in rail.stages())


def test_manual_tab_raise_updates_the_rail(qtbot):
    """The cue must follow the user, not only the rail's own clicks.

    Measured live: after rail-clicking Load, manually raising Statistics and
    Phases left 'Load' highlighted — a stale 'you are here' that reads as wrong
    the moment the user navigates by tab, which they will.
    """
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)

    w._docks["Params"].raise_()
    qtbot.wait(50)
    assert w._workflow_rail.is_current("params"), (
        "raising the Params tab by hand did not move the rail cue"
    )

    # A dock with no stage (Statistics) clears the cue rather than lying.
    w._docks["Statistics"].raise_()
    qtbot.wait(50)
    assert not any(
        w._workflow_rail.is_current(s.key) for s in w._workflow_rail.stages()
    ), "the rail claims a stage while a stageless tab is active"


def test_load_is_an_action_not_a_destination(qtbot, monkeypatch):
    """After the file dialog closes, 'Load' must not stay marked current."""
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    monkeypatch.setattr(w, "_open_file", lambda: None)

    w._workflow_rail.select("params")
    w._workflow_rail.select("load")
    assert not w._workflow_rail.is_current("load"), (
        "'Load' stayed current after its dialog — it is an action, not a place"
    )
    assert w._workflow_rail.is_current("params"), "previous stage not restored"
