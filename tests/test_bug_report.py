"""The Report Bug link must always fit a browser/GitHub URL.

GitHub rejects request lines past ~8KB with a 414, so a log tail embedded in
the new-issue URL must be trimmed to a hard budget — the button otherwise
opens an error page and looks dead.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

from pagb_reconstruction.utils.bug_report import MAX_URL_LEN, issue_url

BASE = "https://github.com/AlanBlanchet/pagb-reconstruction/issues/new"
TEMPLATE = "**Describe the bug**\n\n---\n**Recent log**\n```\n{log}\n```\n"


def _body(url: str) -> str:
    return parse_qs(urlsplit(url).query)["body"][0]


def test_huge_log_still_fits_budget():
    log = "\n".join(f"line {i}: " + "x" * 2000 for i in range(60))
    url = issue_url(BASE, TEMPLATE, log)
    assert len(url) <= MAX_URL_LEN
    assert url.startswith(BASE + "?")


def test_small_log_kept_verbatim_without_note():
    log = "2026-07-21 INFO app: started\n2026-07-21 ERROR core: boom"
    url = issue_url(BASE, TEMPLATE, log)
    body = _body(url)
    assert log in body
    assert "truncated" not in body


def test_trimming_keeps_newest_lines_and_says_so():
    lines = [f"line {i}: " + "x" * 400 for i in range(60)]
    url = issue_url(BASE, TEMPLATE, "\n".join(lines))
    body = _body(url)
    assert lines[-1] in body, "newest log line must survive trimming"
    assert lines[0] not in body, "oldest lines are the ones dropped"
    assert "truncated" in body


def test_single_monster_line_cannot_blow_the_budget():
    url = issue_url(BASE, TEMPLATE, "x" * 50_000)
    assert len(url) <= MAX_URL_LEN


def test_empty_log():
    url = issue_url(BASE, TEMPLATE, "")
    assert len(url) <= MAX_URL_LEN
    assert "**Describe the bug**" in _body(url)


@pytest.mark.parametrize("n_chars", [100, 3000, 20_000, 200_000])
def test_budget_holds_across_log_sizes(n_chars):
    log = "\n".join("y" * 80 for _ in range(n_chars // 80))
    assert len(issue_url(BASE, TEMPLATE, log)) <= MAX_URL_LEN


def test_report_bug_action_emits_bounded_url(qtbot, monkeypatch, tmp_path):
    """End to end: the real handler, a real oversized log file, the real URL."""
    import logging

    monkeypatch.setenv("PAGB_LOG_DIR", str(tmp_path))
    from pagb_reconstruction.utils import logging_setup

    logging_setup.reset()
    logging_setup.setup_logging()
    log = logging.getLogger("pagb_reconstruction")
    for i in range(80):
        log.error("huge diagnostic %d: %s", i, "z" * 1500)

    from PySide6.QtGui import QDesktopServices

    from pagb_reconstruction.ui.main_window import MainWindow

    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", staticmethod(lambda u: opened.append(u.toString()))
    )

    w = MainWindow()
    qtbot.addWidget(w)
    w._report_bug()

    logging_setup.reset()
    assert opened, "Report Bug did not open any URL"
    assert len(opened[0]) <= MAX_URL_LEN, f"URL is {len(opened[0])} chars"
    # The browser can open behind the app — the click must leave visible feedback.
    assert w.statusBar().currentMessage(), "no in-app feedback after Report Bug"
    assert "Bug report opened" in w._log_text.toPlainText(), "no Log-panel line"
