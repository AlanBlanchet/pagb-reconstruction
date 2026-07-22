"""Workspace profiles — named dock layouts that auto-arrange the window.

A profile declares WHICH docks are visible and which is raised in each tabbed
group; applying one is a single call. The window auto-switches to ``Analyze``
when a reconstruction finishes, so results are laid out without manual dock
juggling.
"""

from pydantic import BaseModel


class WorkspaceProfile(BaseModel):
    name: str
    icon: str  # semantic icon name (ui.theme.icons registry)
    visible: tuple[str, ...]
    raised_right: str | None = None
    raised_bottom: str | None = None
    bottom_height: int = 230
    right_width: int = 320


PROFILES: dict[str, WorkspaceProfile] = {
    "Explore": WorkspaceProfile(
        name="Explore",
        icon="open",
        visible=("Phases", "OR", "Params", "Info"),
        raised_right="Phases",
    ),
    "Reconstruct": WorkspaceProfile(
        name="Reconstruct",
        icon="run",
        visible=("Phases", "OR", "Params", "Info", "Reconstruction", "Log"),
        raised_right="Params",
        raised_bottom="Reconstruction",
        bottom_height=200,
    ),
    "Analyze": WorkspaceProfile(
        name="Analyze",
        icon="stats",
        # Every result panel a finished reconstruction produces. A dock left out
        # here is HIDDEN the moment this profile auto-applies, which is how
        # Summary / Misorientation / Parents vanished on completing a run.
        visible=("Phases", "OR", "Params", "Info",
                 "Statistics", "Summary", "Misorientation", "Parents",
                 "Poles", "Reconstruction", "Log"),
        raised_right="Info",
        raised_bottom="Statistics",
        bottom_height=480,
    ),
    "Map only": WorkspaceProfile(
        name="Map only",
        icon="fit",
        visible=(),
    ),
}


def apply_profile(window, profile: WorkspaceProfile) -> None:
    """Apply a workspace layout. Re-applies tab-bar settings afterwards: Qt
    rebuilds tab bars when docks are re-tabified, losing them otherwise."""
    """Arrange *window*'s docks to match *profile*."""
    from PySide6.QtCore import Qt

    for name, dock in window._docks.items():
        dock.setVisible(name in profile.visible)
    if profile.raised_right:
        window._docks[profile.raised_right].raise_()
    # A profile owns WHICH docks are visible and which is raised. It owns their
    # SIZE only as a fallback: when the user has a restored layout, overriding it
    # here silently discarded their saved geometry the instant a reconstruction
    # finished (Analyze's bottom_height stomping a 763px dock back to 493px).
    # Dock geometry has several independent resizeDocks callers; each one must
    # defer to a restored layout or the next one resurfaces this same bug.
    keep_user_geometry = getattr(window, "_layout_restored", False)

    if profile.raised_bottom:
        dock = window._docks[profile.raised_bottom]
        dock.raise_()
        if not keep_user_geometry:
            window.resizeDocks(
                [dock], [profile.bottom_height], Qt.Orientation.Vertical
            )
    if profile.visible and not keep_user_geometry:
        first_right = next(
            (n for n in ("Phases", "OR", "Params", "Info") if n in profile.visible),
            None,
        )
        if first_right:
            window.resizeDocks(
                [window._docks[first_right]], [profile.right_width],
                Qt.Orientation.Horizontal,
            )

    fixup = getattr(window, "_make_dock_tabs_scrollable", None)
    if callable(fixup):
        fixup()
