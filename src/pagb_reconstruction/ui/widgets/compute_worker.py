import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class ComputeWorker(QThread):
    """Run one callable off the UI thread.

    The result signal is deliberately NOT called ``finished``: that name would
    shadow ``QThread.finished``, which is the only reliable hook for knowing when
    the thread has actually stopped — and callers need it to keep a reference
    alive until then. Dropping a still-running QThread makes Qt abort the process
    with "QThread: Destroyed while thread is still running".
    """

    result = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            self.result.emit(self._fn(*self._args))
        except Exception as e:  # noqa: BLE001 — surfaced to the UI, and logged
            logger.exception("Background computation failed")
            self.error.emit(str(e))
