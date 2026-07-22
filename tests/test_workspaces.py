"""Workspace profiles: named dock layouts that auto-arrange the window."""


def test_profiles_reference_real_docks(qtbot):
    """Derive the dock set from the real window, never a hand-written list.

    A hard-coded set here silently blesses the drift it exists to catch: it
    passed while three real docks were missing from every profile.
    """
    from pagb_reconstruction.ui.main_window import MainWindow
    from pagb_reconstruction.ui.workspaces import PROFILES

    w = MainWindow()
    qtbot.addWidget(w)
    known = set(w._docks)
    assert PROFILES, "no profiles defined"
    for prof in PROFILES.values():
        assert set(prof.visible) <= known, prof.name
        assert prof.raised_right in prof.visible or prof.raised_right is None
        assert prof.raised_bottom in prof.visible or prof.raised_bottom is None


def test_apply_profile_shows_and_hides(qapp):
    from pagb_reconstruction.ui.main_window import MainWindow
    from pagb_reconstruction.ui.workspaces import PROFILES, apply_profile

    w = MainWindow()
    w.show()
    qapp.processEvents()

    prof = PROFILES["Reconstruct"]
    apply_profile(w, prof)
    qapp.processEvents()
    for name, dock in w._docks.items():
        assert dock.isVisible() == (name in prof.visible), name

    apply_profile(w, PROFILES["Analyze"])
    qapp.processEvents()
    assert w._docks["Statistics"].isVisible()


def test_every_dock_appears_in_some_profile(qtbot):
    """A dock named in no profile is hidden by the first profile applied.

    apply_profile() sets visibility from a hard-coded name tuple, so any dock
    added later is silently switched off — measured live as Summary /
    Misorientation / Parents vanishing the moment a reconstruction finished and
    the Analyze profile was auto-applied.
    """
    from pagb_reconstruction.ui.main_window import MainWindow
    from pagb_reconstruction.ui.workspaces import PROFILES

    w = MainWindow()
    qtbot.addWidget(w)

    covered = set()
    for profile in PROFILES.values():
        covered |= set(profile.visible)

    orphans = sorted(set(w._docks) - covered)
    assert not orphans, (
        f"docks in no profile at all: {orphans} — the first profile applied "
        "hides them and the View menu is the only way back"
    )


def test_analyze_profile_shows_the_result_docks(qtbot):
    """Analyze is auto-applied when a reconstruction finishes, so it must show
    the panels that present the result the user just waited for."""
    from pagb_reconstruction.ui.workspaces import PROFILES

    visible = set(PROFILES["Analyze"].visible)
    for name in ("Statistics", "Summary", "Misorientation", "Parents", "Poles"):
        assert name in visible, f"Analyze hides {name}, a reconstruction result panel"


def test_profile_does_not_stomp_a_restored_layout(qtbot):
    """A profile may change WHICH docks show, never how big a restored one is.

    Guarding only _fit_layout_to_map_aspect left apply_profile free to override:
    the layout restored correctly, looked right mid-reconstruction, then
    Analyze's bottom_height=480 reset it the instant the run finished. Geometry
    has three independent resizeDocks callers; a guard on one is not a fix.
    """
    from pagb_reconstruction.ui.main_window import MainWindow
    from pagb_reconstruction.ui.workspaces import PROFILES, apply_profile

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    qtbot.wait(50)
    w._layout_restored = True

    # Assert the CALL, not the resulting pixels: offscreen, Qt clamps the dock
    # at the tallest tab's sizeHint so neither a user resize nor the profile's
    # override actually moves it, and a height assertion passes vacuously. The
    # live app is where the override bites, so the observable contract here is
    # that the geometry call is never made.
    calls = []
    real = w.resizeDocks
    w.resizeDocks = lambda *a, **k: calls.append(a)

    apply_profile(w, PROFILES["Analyze"])
    w.resizeDocks = real

    assert not calls, (
        f"apply_profile resized a restored layout: {calls} — the user's saved "
        "geometry is discarded the moment a reconstruction finishes"
    )
    # ...but the profile's VISIBILITY choices must still take effect.
    for name in PROFILES["Analyze"].visible:
        assert not w._docks[name].isHidden(), f"{name} not shown by the profile"
