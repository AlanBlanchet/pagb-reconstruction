import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pagb_reconstruction.ui.main_window import MainWindow
from pagb_reconstruction.ui.theme import apply_theme


def main():
    # Support diagnostic: which compute backend + device is live, without booting
    # Qt. Lets a user confirm whether their GPU is actually being used.
    if "--gpu-check" in sys.argv:
        from pagb_reconstruction.utils.compute import Quaternions

        print(f"compute_backend: {Quaternions.__name__}")
        print(f"compute_device: {getattr(Quaternions, 'device', 'cpu')}")
        try:
            from numba import cuda

            print(f"cuda_available: {cuda.is_available()}")
            if cuda.is_available():
                gpu = cuda.get_current_device()
                print(f"gpu: {gpu.name.decode() if isinstance(gpu.name, bytes) else gpu.name}")
        except Exception as e:  # noqa: BLE001 — diagnostic must never crash
            print(f"cuda_available: False ({type(e).__name__}: {e})")
        return

    # CI smoke for the frozen build: boot Qt + theme + main window offscreen,
    # exit 0. Catches missing bundled assets (the v0.6.0 launch crash) before
    # a release ships.
    smoke = "--smoke" in sys.argv
    if smoke:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([a for a in sys.argv if a != "--smoke"])
    apply_theme(app)
    window = MainWindow()
    if smoke:
        window.show()
        QTimer.singleShot(800, app.quit)
        app.exec()
        print("smoke OK")
        return
    window.show()
    if len(sys.argv) > 1:
        window._load_file(Path(sys.argv[1]))
        if "--run" in sys.argv:
            QTimer.singleShot(500, window._run_reconstruction)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
