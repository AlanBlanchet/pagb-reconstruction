"""Frozen-build packaging guards.

Data files the app reads at runtime (the SCSS stylesheet, qtawesome fonts) must
be (a) loaded via a frozen-safe API and (b) declared in the PyInstaller specs —
otherwise the shipped .exe crashes on launch with FileNotFoundError. This is a
regression guard for exactly that crash.
"""

from importlib.resources import files
from pathlib import Path


def test_app_scss_is_a_package_resource():
    # Must resolve via importlib.resources (works when frozen), not just __file__.
    res = files("pagb_reconstruction.ui.theme").joinpath("app.scss")
    assert res.is_file()
    assert res.read_text(encoding="utf-8").strip()


def test_specs_bundle_scss_and_qtawesome():
    for spec in ("pagb.spec", "pagb-onefile.spec"):
        txt = Path(spec).read_text()
        assert "app.scss" in txt, f"{spec} does not bundle app.scss"
        assert "qtawesome" in txt, f"{spec} does not collect qtawesome data"
