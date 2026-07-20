"""ComputeWorker must not shadow QThread.finished.

Callers need the built-in QThread.finished to know when a thread has actually
stopped, so they can hold a reference until then. Dropping a running QThread
makes Qt abort the process ("QThread: Destroyed while thread is still running"),
which is a hard crash a user hits by switching display mode mid-computation.
"""

from PySide6.QtCore import QThread

from pagb_reconstruction.ui.widgets.compute_worker import ComputeWorker


def test_result_signal_does_not_shadow_qthread_finished(qtbot):
    worker = ComputeWorker(lambda: 42)
    # QThread.finished must still be the real lifetime signal, not overridden
    assert type(worker).finished is QThread.finished


def test_emits_result(qtbot):
    worker = ComputeWorker(lambda: 42)
    with qtbot.waitSignal(worker.result, timeout=5000) as blocker:
        worker.start()
    assert blocker.args == [42]
    worker.wait(5000)


def test_emits_error_on_exception(qtbot):
    def boom():
        raise ValueError("kaboom")

    worker = ComputeWorker(boom)
    with qtbot.waitSignal(worker.error, timeout=5000) as blocker:
        worker.start()
    assert "kaboom" in blocker.args[0]
    worker.wait(5000)


def test_finished_fires_after_run(qtbot):
    worker = ComputeWorker(lambda: 1)
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    assert not worker.isRunning()
