"""The app must write everything it logs to one file the user can hand back.

Without this, logger output and uncaught exceptions vanish and a bug report
carries no evidence.
"""

import logging

from pagb_reconstruction.utils import logging_setup


def test_log_path_honours_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    assert logging_setup.log_file_path().parent == tmp_path
    assert logging_setup.log_file_path().name.endswith(".log")


def test_setup_writes_records_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    logging_setup.reset()
    path = logging_setup.setup_logging()
    logging.getLogger("pagb_reconstruction.test").warning("hello-from-test")
    logging_setup.flush()
    assert "hello-from-test" in path.read_text()


def test_uncaught_exception_is_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    logging_setup.reset()
    path = logging_setup.setup_logging()
    try:
        raise ValueError("boom-uncaught")
    except ValueError:
        import sys

        logging_setup._log_excepthook(*sys.exc_info())
    logging_setup.flush()
    text = path.read_text()
    assert "boom-uncaught" in text
    assert "Traceback" in text


def test_tail_returns_recent_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    logging_setup.reset()
    logging_setup.setup_logging()
    log = logging.getLogger("pagb_reconstruction.tail")
    for i in range(50):
        log.info("line-%d", i)
    logging_setup.flush()
    tail = logging_setup.tail(10)
    assert "line-49" in tail
    assert "line-0" not in tail
    assert len(tail.splitlines()) <= 10


def test_setup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    logging_setup.reset()
    logging_setup.setup_logging()
    logging_setup.setup_logging()
    import logging.handlers

    root = logging.getLogger()
    ours = [
        h for h in root.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
        and h.baseFilename == str(logging_setup.log_file_path())
    ]
    assert len(ours) == 1, "repeated setup must not duplicate handlers"
