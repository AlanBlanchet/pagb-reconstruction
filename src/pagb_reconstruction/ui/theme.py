import qdarktheme
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication):
    qdarktheme.setup_theme("auto")
