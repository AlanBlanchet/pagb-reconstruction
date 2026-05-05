import pyqtgraph as pg
import qdarktheme
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from pydantic import BaseModel
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


class ThemePalette(BaseModel):
    name: str
    bg: str
    fg: str
    surface: str
    surface_dim: str
    border: str
    accent: str
    accent_alt: str
    text_muted: str
    text_disabled: str
    success: str
    warning: str
    error: str
    info: str

    def bg_rgb(self) -> tuple[int, int, int]:
        return int(self.bg[1:3], 16), int(self.bg[3:5], 16), int(self.bg[5:7], 16)

    @property
    def is_light(self) -> bool:
        r, g, b = self.bg_rgb()
        return (0.299 * r + 0.587 * g + 0.114 * b) > 128


THEMES: dict[str, ThemePalette] = {
    "Catppuccin Mocha": ThemePalette(
        name="Catppuccin Mocha",
        bg="#1e1e2e",
        fg="#cdd6f4",
        surface="#313244",
        surface_dim="#181825",
        border="#45475a",
        accent="#89b4fa",
        accent_alt="#74c7ec",
        text_muted="#a6adc8",
        text_disabled="#585b70",
        success="#a6e3a1",
        warning="#fab387",
        error="#f38ba8",
        info="#94e2d5",
    ),
    "Catppuccin Latte": ThemePalette(
        name="Catppuccin Latte",
        bg="#eff1f5",
        fg="#4c4f69",
        surface="#ccd0da",
        surface_dim="#e6e9ef",
        border="#9ca0b0",
        accent="#1e66f5",
        accent_alt="#209fb5",
        text_muted="#6c6f85",
        text_disabled="#9ca0b0",
        success="#40a02b",
        warning="#fe640b",
        error="#d20f39",
        info="#179299",
    ),
    "Nord": ThemePalette(
        name="Nord",
        bg="#2e3440",
        fg="#eceff4",
        surface="#3b4252",
        surface_dim="#242933",
        border="#4c566a",
        accent="#88c0d0",
        accent_alt="#81a1c1",
        text_muted="#d8dee9",
        text_disabled="#4c566a",
        success="#a3be8c",
        warning="#ebcb8b",
        error="#bf616a",
        info="#8fbcbb",
    ),
    "Solarized Dark": ThemePalette(
        name="Solarized Dark",
        bg="#002b36",
        fg="#839496",
        surface="#073642",
        surface_dim="#001e26",
        border="#586e75",
        accent="#268bd2",
        accent_alt="#2aa198",
        text_muted="#657b83",
        text_disabled="#586e75",
        success="#859900",
        warning="#b58900",
        error="#dc322f",
        info="#2aa198",
    ),
}

_active: ThemePalette = THEMES["Catppuccin Mocha"]

DARK_BG = _active.bg
DARK_FG = _active.fg
GRID_COLOR = _active.border
ACCENT = _active.accent
EDGE_COLOR = _active.surface
SURFACE_DIM = _active.surface_dim
TEXT_MUTED = _active.text_muted
TEXT_DISABLED = _active.text_disabled


def _sync_globals():
    global DARK_BG, DARK_FG, GRID_COLOR, ACCENT, EDGE_COLOR, SURFACE_DIM, TEXT_MUTED, TEXT_DISABLED
    DARK_BG = _active.bg
    DARK_FG = _active.fg
    GRID_COLOR = _active.border
    ACCENT = _active.accent
    EDGE_COLOR = _active.surface
    SURFACE_DIM = _active.surface_dim
    TEXT_MUTED = _active.text_muted
    TEXT_DISABLED = _active.text_disabled


def active_theme() -> ThemePalette:
    return _active


def set_theme(name: str, app: QApplication):
    global _active
    _active = THEMES[name]
    _sync_globals()
    _apply_active(app)
    settings = QSettings("PAGB", "pagb-reconstruction")
    settings.setValue("theme", name)


def _build_stylesheet(p: ThemePalette) -> str:
    return f"""
QGroupBox {{
    font-weight: bold;
    border: 1px solid {p.border};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: {p.accent};
}}
QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: 2px;
}}
QTabBar::tab {{
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background: {p.surface};
    color: {p.accent};
    border-bottom: 2px solid {p.accent};
}}
QTabBar::tab:!selected {{
    background: {p.bg};
    color: {p.text_muted};
}}
QTabBar::tab:hover:!selected {{
    background: {p.surface_dim};
}}
QPushButton {{
    padding: 5px 14px;
    border-radius: 4px;
    border: 1px solid {p.border};
    background: {p.surface};
    color: {p.fg};
}}
QPushButton:hover {{
    background: {p.border};
    border-color: {p.accent};
}}
QPushButton:pressed {{
    background: {p.text_disabled};
}}
QPushButton:disabled {{
    background: {p.bg};
    color: {p.text_disabled};
    border-color: {p.surface};
}}
QProgressBar {{
    border: 1px solid {p.border};
    border-radius: 4px;
    text-align: center;
    background: {p.bg};
    color: {p.fg};
    height: 18px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.accent}, stop:1 {p.accent_alt});
    border-radius: 3px;
}}
QToolBar {{
    spacing: 4px;
    padding: 2px;
    border-bottom: 1px solid {p.surface};
}}
QStatusBar {{
    border-top: 1px solid {p.surface};
    color: {p.text_muted};
    font-size: 12px;
}}
QDockWidget {{
    titlebar-close-icon: none;
    font-weight: bold;
}}
QDockWidget::title {{
    background: {p.surface_dim};
    padding: 4px 8px;
    border-bottom: 1px solid {p.surface};
}}
QComboBox {{
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid {p.border};
    background: {p.surface};
}}
QComboBox:hover {{
    border-color: {p.accent};
}}
QSpinBox, QDoubleSpinBox {{
    padding: 3px 6px;
    border-radius: 4px;
    border: 1px solid {p.border};
    background: {p.surface};
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {p.accent};
}}
"""


CUSTOM_STYLESHEET = _build_stylesheet(_active)


def _apply_active(app: QApplication):
    global CUSTOM_STYLESHEET
    p = _active
    CUSTOM_STYLESHEET = _build_stylesheet(p)
    mode = "light" if p.is_light else "dark"
    try:
        qdarktheme.setup_theme(
            mode,
            corner_shape="sharp",
            custom_colors={
                "primary": p.accent,
                "background": p.bg,
                "foreground": p.fg,
            },
            additional_qss=CUSTOM_STYLESHEET,
        )
    except Exception:
        app.setStyleSheet(CUSTOM_STYLESHEET)
    pg.setConfigOptions(
        background=p.bg,
        foreground=p.fg,
        antialias=True,
    )


def apply_theme(app: QApplication):
    settings = QSettings("PAGB", "pagb-reconstruction")
    saved = settings.value("theme", "Catppuccin Mocha")
    if saved in THEMES:
        global _active
        _active = THEMES[saved]
        _sync_globals()
    _apply_active(app)


def create_figure(figsize: tuple[float, float] = (6, 4)):
    fig = Figure(figsize=figsize)
    fig.set_facecolor(_active.bg)
    canvas = FigureCanvasQTAgg(fig)
    return fig, canvas


create_dark_figure = create_figure


def style_ax(ax):
    p = _active
    ax.set_facecolor(p.bg)
    ax.tick_params(colors=p.fg, labelsize=8)
    ax.xaxis.label.set_color(p.fg)
    ax.yaxis.label.set_color(p.fg)
    ax.title.set_color(p.fg)
    ax.title.set_fontsize(10)
    for spine in ax.spines.values():
        spine.set_color(p.border)
    ax.grid(True, alpha=0.2, color=p.border, linewidth=0.5)
