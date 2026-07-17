"""Theming: typed palettes -> SCSS -> Qt QSS, plus a semantic icon registry."""

from pagb_reconstruction.ui.theme.engine import (
    active_theme,
    apply_theme,
    create_figure,
    set_theme,
    style_ax,
)
from pagb_reconstruction.ui.theme.icons import icon
from pagb_reconstruction.ui.theme.palette import THEMES, ThemePalette

__all__ = [
    "THEMES",
    "ThemePalette",
    "active_theme",
    "apply_theme",
    "set_theme",
    "create_figure",
    "style_ax",
    "icon",
]
