import json
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

REPO = "AlanBlanchet/pagb-reconstruction"


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str


class UpdateChecker(QThread):
    update_available = Signal(object)

    def run(self):
        try:
            url = f"https://api.github.com/repos/{REPO}/releases/latest"
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                data = json.loads(resp.read())
            remote = data["tag_name"].lstrip("v")
            from pagb_reconstruction import __version__
            from packaging.version import Version

            if Version(remote) > Version(__version__):
                info = UpdateInfo(
                    version=remote,
                    url=data["html_url"],
                    notes=data.get("body", ""),
                )
                self.update_available.emit(info)
        except Exception:
            pass
