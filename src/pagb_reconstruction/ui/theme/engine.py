"""Theme engine: compile the SCSS stylesheet with the active palette and apply it.

The palette is the single colour source; every ``$var`` in ``app.scss`` is
injected from it here, so a colour only ever lives in :mod:`palette`.
"""

import logging
from pathlib import Path

import pyqtgraph as pg
import qdarktheme
import qtsass
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from pagb_reconstruction.ui.theme.palette import THEMES, ThemePalette

logger = logging.getLogger(__name__)

_SCSS_PATH = Path(__file__).with_name("app.scss")
_DEFAULT = "Carbon"

_active: ThemePalette = THEMES[_DEFAULT]
_qss_cache: dict[str, str] = {}


def _scss_vars(p: ThemePalette) -> str:
    # Every non-name palette field becomes an SCSS variable ($bg, $accent, …).
    lines = [f"${k}: {v};" for k, v in p.model_dump().items() if k != "name"]
    return "\n".join(lines) + "\n"


def _compile(p: ThemePalette) -> str:
    if p.name not in _qss_cache:
        scss = _scss_vars(p) + _SCSS_PATH.read_text(encoding="utf-8")
        _qss_cache[p.name] = qtsass.compile(scss)
    return _qss_cache[p.name]


def active_theme() -> ThemePalette:
    return _active


def _apply(app: QApplication) -> None:
    p = _active
    qss = _compile(p)
    mode = "light" if p.is_light else "dark"
    try:
        qdarktheme.setup_theme(
            mode,
            corner_shape="rounded",
            custom_colors={"primary": p.accent, "background": p.bg, "foreground": p.fg},
            additional_qss=qss,
        )
    except Exception:
        logger.warning("qdarktheme setup failed; applying raw QSS", exc_info=True)
        app.setStyleSheet(qss)
    pg.setConfigOptions(background=p.surface_dim, foreground=p.fg, antialias=True)


def set_theme(name: str, app: QApplication) -> None:
    global _active
    if name not in THEMES:
        return
    _active = THEMES[name]
    _apply(app)
    QSettings("PAGB", "pagb-reconstruction").setValue("theme", name)


def apply_theme(app: QApplication) -> None:
    global _active
    saved = QSettings("PAGB", "pagb-reconstruction").value("theme", _DEFAULT)
    _active = THEMES.get(saved, THEMES[_DEFAULT])
    _apply(app)


# ── Matplotlib helpers ──────────────────────────────────────────────
def create_figure(figsize: tuple[float, float] = (6, 4)):
    fig = Figure(figsize=figsize)
    fig.set_facecolor(_active.surface_dim)
    return fig, FigureCanvasQTAgg(fig)


def style_ax(ax) -> None:
    p = _active
    ax.set_facecolor(p.surface_dim)
    ax.tick_params(colors=p.fg, labelsize=8)
    ax.xaxis.label.set_color(p.fg)
    ax.yaxis.label.set_color(p.fg)
    ax.title.set_color(p.fg)
    ax.title.set_fontsize(10)
    for spine in ax.spines.values():
        spine.set_color(p.border)
    ax.grid(True, alpha=0.18, color=p.border, linewidth=0.5)
