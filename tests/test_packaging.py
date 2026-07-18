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


def test_specs_exclude_torch():
    # torch is an optional GPU accelerator (numpy fallback otherwise); bundling
    # its ~700 MB into the desktop build is a regression — keep it excluded.
    for spec in ("pagb.spec", "pagb-onefile.spec"):
        txt = Path(spec).read_text()
        assert '"torch"' in txt and "excludes" in txt, f"{spec} must exclude torch"


def test_compute_falls_back_without_torch():
    # The numpy backend must be a complete, working path (the frozen build runs
    # it when torch is excluded).
    from pagb_reconstruction.utils.compute import _NumpyQuaternions

    import numpy as np

    q = np.array([[1.0, 0, 0, 0], [0.0, 1, 0, 0]])
    sym = np.array([[1.0, 0, 0, 0]])
    below = _NumpyQuaternions.pairwise_below(q, sym, 200.0)
    assert below.shape == (2, 2) and bool(below[0, 1])
