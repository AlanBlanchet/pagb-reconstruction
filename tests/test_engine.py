"""The SCSS engine must compile every theme to variable-free QSS."""

import pytest

from pagb_reconstruction.ui.theme.engine import _compile, _scss_vars
from pagb_reconstruction.ui.theme.palette import THEMES, ThemePalette


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_scss_compiles_to_variable_free_qss(theme: ThemePalette):
    qss = _compile(theme)
    assert qss.strip(), "empty stylesheet"
    assert "$" not in qss, "unresolved SCSS variable leaked into QSS"
    # the accent must survive into the output (progress chunk, focus, …)
    assert theme.accent.lower() in qss.lower()


def test_compile_falls_back_on_error(monkeypatch):
    # A stylesheet read/compile failure must NOT crash the app — return "" so
    # the base theme still applies (guards the frozen-launch crash class).
    import pagb_reconstruction.ui.theme.engine as eng

    eng._qss_cache.pop("Carbon", None)

    def boom(_):
        raise RuntimeError("simulated missing app.scss")

    monkeypatch.setattr(eng, "_scss_vars", boom)
    try:
        assert eng._compile(THEMES["Carbon"]) == ""
    finally:
        eng._qss_cache.pop("Carbon", None)


def test_scss_vars_cover_every_palette_colour():
    p = THEMES["Carbon"]
    vars_block = _scss_vars(p)
    for field, value in p.model_dump().items():
        if field == "name":
            continue
        assert f"${field}: {value};" in vars_block
