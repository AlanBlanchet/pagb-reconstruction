"""Build the GitHub new-issue link for the in-app bug reporter.

GitHub (and some platform URL handlers) reject request lines past ~8KB, so a
log tail percent-encoded into the URL must fit a hard budget — an oversized
link opens a 414 error page and the Report Bug button looks dead. The log is
the only unbounded part of the report: it is trimmed oldest-line-first until
the encoded URL fits, with a note pointing at the full log file.
"""

from urllib.parse import quote

MAX_URL_LEN = 6000  # conservative vs GitHub's ~8KB request-line cap
_MAX_LINE = 500  # one runaway line must not eat the whole budget
_TRUNCATION_NOTE = "… log truncated to fit the URL — attach the full file (Help > Open Log File)"


def issue_url(new_issue_url: str, body_template: str, log_tail: str, max_len: int = MAX_URL_LEN) -> str:
    """Fill ``{log}`` in *body_template* with as much of *log_tail* as fits.

    Newest lines are kept; the template itself is assumed bounded. The slot is
    filled by literal replacement, not str.format — dynamic env values in the
    template may carry braces.
    """
    lines = [line[:_MAX_LINE] for line in log_tail.splitlines()]
    truncated = False
    while True:
        block = "\n".join(([_TRUNCATION_NOTE] if truncated else []) + lines)
        url = f"{new_issue_url}?title=&body={quote(body_template.replace('{log}', block))}"
        if len(url) <= max_len or not lines:
            return url
        truncated = True
        lines = lines[1:]
