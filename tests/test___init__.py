"""Theme package public-API contract (re-export surface of ui/theme/__init__.py)."""

_PUBLIC = (
    "apply_theme", "set_theme", "active_theme", "THEMES", "ThemePalette",
    "icon", "create_figure", "style_ax",
)


def test_theme_public_api_is_importable():
    from pagb_reconstruction.ui import theme

    for name in _PUBLIC:
        assert hasattr(theme, name), f"missing public symbol: {name}"
    assert theme.active_theme().name in theme.THEMES
