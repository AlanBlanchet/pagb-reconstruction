"""One log file for the whole application.

Everything the app reports — module loggers, Qt's own warnings, and any uncaught
exception — is funnelled into a single rotating file the user can attach to a bug
report. Before this existed, ``logger.error(...)`` calls and crashes in Qt slots
went nowhere, so a report from the field carried no evidence of what happened.

The file lives in the user's data directory (``PAGB_LOG_DIR`` overrides it) and
rotates so it cannot grow without bound.
"""

import logging
import logging.handlers
import os
import platform
import sys
from pathlib import Path

_APP = "pagb-reconstruction"
_MAX_BYTES = 2_000_000
_BACKUPS = 3

_file_handler: logging.Handler | None = None
_previous_excepthook = None


def log_dir() -> Path:
    override = os.environ.get("PAGB_LOG_DIR")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / _APP / "logs"


def log_file_path() -> Path:
    return log_dir() / "pagb.log"


def _log_excepthook(exc_type, exc, tb) -> None:
    """Send an otherwise-silent crash to the log before the default handler."""
    logging.getLogger("pagb_reconstruction").critical(
        "Uncaught exception", exc_info=(exc_type, exc, tb)
    )
    if _previous_excepthook is not None:
        _previous_excepthook(exc_type, exc, tb)


def _install_qt_handler() -> None:
    """Route Qt's own warnings into the same file (they otherwise go to stderr,
    which a windowed build discards)."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:  # noqa: BLE001 — logging must never block start-up
        return

    log = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message):
        log.log(levels.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(handler)


def setup_logging(level: int = logging.INFO) -> Path:
    """Attach the rotating file handler and capture crashes. Idempotent."""
    global _file_handler, _previous_excepthook

    path = log_file_path()
    if _file_handler is not None:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _file_handler = handler

    if sys.excepthook is not _log_excepthook:
        _previous_excepthook = sys.excepthook
        sys.excepthook = _log_excepthook
    _install_qt_handler()

    logging.getLogger(__name__).info("--- session start (log: %s) ---", path)
    return path


def flush() -> None:
    if _file_handler is not None:
        _file_handler.flush()


def tail(lines: int = 200) -> str:
    """Last *lines* of the log — what a bug report should carry."""
    flush()
    path = log_file_path()
    if not path.exists():
        return "(no log file)"
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:  # noqa: BLE001
        return f"(could not read log: {e})"
    return "\n".join(content[-lines:])


def reset() -> None:
    """Detach the handler — for tests, so each one gets a fresh file."""
    global _file_handler, _previous_excepthook
    root = logging.getLogger()
    if _file_handler is not None:
        _file_handler.close()
        root.removeHandler(_file_handler)
        _file_handler = None
    if _previous_excepthook is not None:
        sys.excepthook = _previous_excepthook
        _previous_excepthook = None
