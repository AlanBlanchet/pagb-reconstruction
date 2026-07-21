"""Semantic vector-icon registry (Phosphor, via qtawesome).

Widgets ask for icons by MEANING (``icon("run")``), never by glyph or Qt
standard-pixmap enum. Colour defaults to the active theme's foreground so icons
stay legible across every palette; pass ``color=`` for accent/state icons.
"""

import logging

import qtawesome as qta
from PySide6.QtGui import QIcon

from pagb_reconstruction.ui.theme.engine import active_theme

logger = logging.getLogger(__name__)

# semantic name -> Phosphor icon id (all verified present in qtawesome)
_REGISTRY: dict[str, str] = {
    "open": "ph.folder-open",
    "save": "ph.floppy-disk",
    "run": "ph.play",
    "stop": "ph.stop",
    "zoom_in": "ph.magnifying-glass-plus",
    "zoom_out": "ph.magnifying-glass-minus",
    "fit": "ph.arrows-out",
    "export_image": "ph.image",
    "export_data": "ph.export",
    "split": "ph.columns",
    "line_profile": "ph.chart-line",
    "roi": "ph.selection",
    "reset_layout": "ph.layout",
    "clear_roi": "ph.selection-slash",
    "reset": "ph.arrow-counter-clockwise",
    "add": "ph.plus",
    "remove": "ph.trash",
    "measure": "ph.ruler",
    "close": "ph.x",
    "chevron_down": "ph.caret-down",
    "chevron_right": "ph.caret-right",
    "check": "ph.check",
    "cross": "ph.x",
    "boundaries": "ph.polygon",
    "palette": "ph.palette",
    "equalize": "ph.chart-bar",
    "layers": "ph.stack",
    "info": "ph.info",
    "grain": "ph.circles-three",
    "phase": "ph.circles-three",
    "orientation": "ph.compass",
    "params": "ph.sliders-horizontal",
    "stats": "ph.chart-bar-horizontal",
    "poles": "ph.globe-hemisphere-west",
    "log": "ph.list-bullets",
    "theme": "ph.paint-brush",
    "bug": "ph.bug",
    "about": "ph.info",
    "spinner": "ph.spinner-gap",
}


def icon(name: str, color: str | None = None) -> QIcon:
    """Themed vector icon for a semantic name; falls back to an empty icon."""
    spec = _REGISTRY.get(name)
    if spec is None:
        logger.warning("unknown icon name %r — rendering blank", name)
        return QIcon()
    return qta.icon(spec, color=color or active_theme().fg)
