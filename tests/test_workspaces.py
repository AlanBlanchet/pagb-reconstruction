"""Workspace profiles: named dock layouts that auto-arrange the window."""


def test_profiles_reference_real_docks():
    from pagb_reconstruction.ui.workspaces import PROFILES

    known = {"Phases", "OR", "Params", "Info",
             "Reconstruction", "Statistics", "Poles", "Log"}
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
