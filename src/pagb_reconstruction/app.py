import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pagb_reconstruction.ui.main_window import MainWindow
from pagb_reconstruction.ui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window._load_file(Path(sys.argv[1]))
        if "--run" in sys.argv:
            QTimer.singleShot(500, window._run_reconstruction)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
