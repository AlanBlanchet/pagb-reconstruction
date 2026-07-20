"""Updater helpers — release asset selection per platform."""

import platform

from pagb_reconstruction.core import updater


def test_find_asset_url_picks_platform_binary(monkeypatch):
    assets = [
        {"name": "pagb-reconstruction.exe", "browser_download_url": "win"},
        {"name": "pagb-reconstruction.AppImage", "browser_download_url": "lin"},
    ]
    monkeypatch.setattr(updater.platform, "system", lambda: "Windows")
    assert updater._find_asset_url(assets) == "win"
    monkeypatch.setattr(updater.platform, "system", lambda: "Linux")
    assert updater._find_asset_url(assets) == "lin"


def test_find_asset_url_empty_when_no_match(monkeypatch):
    monkeypatch.setattr(updater.platform, "system", lambda: "Windows")
    assert updater._find_asset_url([{"name": "notes.txt", "browser_download_url": "x"}]) == ""
