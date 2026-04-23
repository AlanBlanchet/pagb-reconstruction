from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import pyqtgraph as pg
import qdarktheme
from PySide6.QtWidgets import QApplication

DARK_BG = "#1e1e2e"
DARK_FG = "#cdd6f4"
GRID_COLOR = "#45475a"
ACCENT = "#89b4fa"
EDGE_COLOR = "#313244"
SURFACE_DIM = "#181825"
TEXT_MUTED = "#a6adc8"
TEXT_DISABLED = "#585b70"


def create_dark_figure(figsize: tuple[float, float] = (6, 4)) -> tuple[Figure, FigureCanvasQTAgg]:
    fig = Figure(figsize=figsize)
    fig.set_facecolor(DARK_BG)
    canvas = FigureCanvasQTAgg(fig)
    return fig, canvas


def style_ax(ax):
    ax.set_facecolor(DARK_BG)
    ax.tick_params(colors=DARK_FG, labelsize=8)
    ax.xaxis.label.set_color(DARK_FG)
    ax.yaxis.label.set_color(DARK_FG)
    ax.title.set_color(DARK_FG)
    ax.title.set_fontsize(10)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(True, alpha=0.2, color=GRID_COLOR, linewidth=0.5)

CUSTOM_STYLESHEET = """
QGroupBox {
    font-weight: bold;
    border: 1px solid #3a3a4a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #89b4fa;
}
QTabWidget::pane {
    border: 1px solid #3a3a4a;
    border-radius: 2px;
}
QTabBar::tab {
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #313244;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:!selected {
    background: #1e1e2e;
    color: #9399b2;
}
QTabBar::tab:hover:!selected {
    background: #2a2a3c;
}
QPushButton {
    padding: 5px 14px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background: #313244;
    color: #cdd6f4;
}
QPushButton:hover {
    background: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background: #585b70;
}
QPushButton:disabled {
    background: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    background: #1e1e2e;
    color: #cdd6f4;
    height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89b4fa, stop:1 #74c7ec);
    border-radius: 3px;
}
QToolBar {
    spacing: 4px;
    padding: 2px;
    border-bottom: 1px solid #313244;
}
QStatusBar {
    border-top: 1px solid #313244;
    color: #a6adc8;
    font-size: 12px;
}
QDockWidget {
    titlebar-close-icon: none;
    font-weight: bold;
}
QDockWidget::title {
    background: #181825;
    padding: 4px 8px;
    border-bottom: 1px solid #313244;
}
QComboBox {
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background: #313244;
}
QComboBox:hover {
    border-color: #89b4fa;
}
QSpinBox, QDoubleSpinBox {
    padding: 3px 6px;
    border-radius: 4px;
    border: 1px solid #45475a;
    background: #313244;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #89b4fa;
}
"""


def apply_theme(app: QApplication):
    qdarktheme.setup_theme(
        "dark",
        corner_shape="sharp",
        custom_colors={
            "primary": ACCENT,
            "background": DARK_BG,
            "foreground": DARK_FG,
        },
        additional_qss=CUSTOM_STYLESHEET,
    )
    pg.setConfigOptions(
        background=DARK_BG,
        foreground=DARK_FG,
        antialias=True,
    )
