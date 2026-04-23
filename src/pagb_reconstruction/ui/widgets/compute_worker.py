from PySide6.QtCore import QThread, Signal


class ComputeWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
