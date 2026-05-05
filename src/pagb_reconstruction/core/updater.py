import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass

from packaging.version import Version
from PySide6.QtCore import QThread, Signal

from pagb_reconstruction import __version__

REPO = "AlanBlanchet/pagb-reconstruction"


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str
    download_url: str


class UpdateChecker(QThread):
    update_available = Signal(object)

    def run(self):
        try:
            local_ver = Version(__version__)
            if local_ver.is_devrelease or local_ver.is_prerelease:
                return

            url = f"https://api.github.com/repos/{REPO}/releases/latest"
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                data = json.loads(resp.read())
            remote = data["tag_name"].lstrip("v")

            if Version(remote) > local_ver:
                download_url = _find_asset_url(data.get("assets", []))
                info = UpdateInfo(
                    version=remote,
                    url=data["html_url"],
                    notes=data.get("body", ""),
                    download_url=download_url,
                )
                self.update_available.emit(info)
        except Exception:
            pass


class UpdateDownloader(QThread):
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, download_url: str):
        super().__init__()
        self._url = download_url

    def run(self):
        try:
            suffix = ".exe" if platform.system() == "Windows" else ".AppImage"
            fd, dest = tempfile.mkstemp(suffix=suffix)
            os.close(fd)

            req = urllib.request.Request(self._url)  # noqa: S310
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int(downloaded * 100 / total))

            if not dest.endswith(".exe"):
                os.chmod(dest, 0o755)

            self.finished.emit(dest)
        except Exception as e:
            self.error.emit(str(e))


def relaunch_from(binary_path: str):
    subprocess.Popen([binary_path], start_new_session=True)  # noqa: S603
    sys.exit(0)


def _find_asset_url(assets: list[dict]) -> str:
    system = platform.system()
    for asset in assets:
        name = asset.get("name", "").lower()
        if system == "Windows" and name.endswith(".exe"):
            return asset["browser_download_url"]
        if system == "Linux" and name.endswith(".appimage"):
            return asset["browser_download_url"]
    return ""
