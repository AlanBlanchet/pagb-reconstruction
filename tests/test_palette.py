"""Palette invariants: valid hex, tonal-elevation distinctness, WCAG contrast.

Accessibility is a *computable* property, so it is verified by computation here
rather than by eye — every theme must clear the contrast floors below.
"""

import pytest

from pagb_reconstruction.ui.theme.palette import THEMES, ThemePalette

_HEX_FIELDS = [
    "surface_dim", "bg", "surface", "elevated", "border", "border_strong",
    "accent", "accent_hover", "on_accent", "fg", "text_muted", "text_disabled",
    "success", "warning", "error", "info",
]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(p: ThemePalette, field: str) -> float:
    r, g, b = (v / 255 for v in p.rgb(field))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(p: ThemePalette, a: str, b: str) -> float:
    la, lb = _luminance(p, a), _luminance(p, b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_all_fields_valid_hex(theme: ThemePalette):
    for f in _HEX_FIELDS:
        val = getattr(theme, f)
        assert val.startswith("#") and len(val) == 7, f"{theme.name}.{f}={val!r}"
        int(val[1:], 16)  # raises if not hex


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_body_text_meets_wcag_aa(theme: ThemePalette):
    # Primary text on panels must clear AA (4.5:1) for normal text.
    assert _contrast(theme, "fg", "surface") >= 4.5
    assert _contrast(theme, "fg", "bg") >= 4.5


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_muted_and_accent_are_legible(theme: ThemePalette):
    # Muted text and the accent must clear the 3:1 large-text / UI floor.
    assert _contrast(theme, "text_muted", "surface") >= 3.0
    assert _contrast(theme, "accent", "bg") >= 3.0
    assert _contrast(theme, "on_accent", "accent") >= 3.0


@pytest.mark.parametrize("theme", THEMES.values(), ids=list(THEMES))
def test_elevation_tiers_are_distinct(theme: ThemePalette):
    # The four elevation surfaces must be perceptibly different tones.
    tiers = [_luminance(theme, f) for f in ("surface_dim", "bg", "surface", "elevated")]
    for lo, hi in zip(tiers, tiers[1:]):
        assert abs(hi - lo) > 1e-4, f"{theme.name}: adjacent surfaces too close"
