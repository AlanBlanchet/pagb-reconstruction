"""Typed colour palettes — the single source of colour truth for the whole UI.

Elevation is expressed as *surface tone*, never as coloured borders or stripes:
``surface_dim`` (recessed wells) < ``bg`` (base) < ``surface`` (panels) <
``elevated`` (cards / popups). ``accent`` is reserved for the primary action and
selection only.
"""

from typing import Annotated

from pydantic import BaseModel, Field

# A 6-digit hex colour — makes an illegal palette value unrepresentable, so
# rgb()/is_light/_scss_vars can trust every field without defensive parsing.
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class ThemePalette(BaseModel):
    name: str

    # Tonal elevation ladder (low -> high)
    surface_dim: HexColor  # recessed wells: inputs, log, map canvas
    bg: HexColor  # base app background
    surface: HexColor  # raised panels / docks
    elevated: HexColor  # cards, menus, tooltips, popups

    border: HexColor  # subtle hairline
    border_strong: HexColor  # focus / emphasis outline

    accent: HexColor  # primary action + selection ONLY
    accent_hover: HexColor
    on_accent: HexColor  # text/glyph on an accent fill

    fg: HexColor
    text_muted: HexColor
    text_disabled: HexColor

    success: HexColor
    warning: HexColor
    error: HexColor
    info: HexColor

    def rgb(self, field: str) -> tuple[int, int, int]:
        h = getattr(self, field).lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @property
    def is_light(self) -> bool:
        r, g, b = self.rgb("bg")
        return (0.299 * r + 0.587 * g + 0.114 * b) > 128


THEMES: dict[str, ThemePalette] = {
    "Carbon": ThemePalette(
        name="Carbon",
        surface_dim="#141414",
        bg="#191919",
        surface="#232323",
        elevated="#2c2c2c",
        border="#333333",
        border_strong="#4a4a4a",
        accent="#4f8cff",
        accent_hover="#6ba1ff",
        on_accent="#ffffff",
        fg="#e4e4e4",
        text_muted="#8a8a8a",
        text_disabled="#565656",
        success="#46c88a",
        warning="#e0b341",
        error="#f0616d",
        info="#58a6ff",
    ),
    "Slate": ThemePalette(
        name="Slate",
        surface_dim="#0f141c",
        bg="#141b24",
        surface="#1c2531",
        elevated="#26313f",
        border="#2e3a49",
        border_strong="#425061",
        accent="#5aa2ff",
        accent_hover="#7bb6ff",
        on_accent="#0b0f16",
        fg="#dfe6ef",
        text_muted="#8896a8",
        text_disabled="#556072",
        success="#57cc9a",
        warning="#e6b552",
        error="#f2606f",
        info="#6cb2ff",
    ),
    "Catppuccin Mocha": ThemePalette(
        name="Catppuccin Mocha",
        surface_dim="#181825",
        bg="#1e1e2e",
        surface="#28283b",
        elevated="#313244",
        border="#3b3d52",
        border_strong="#52546b",
        accent="#89b4fa",
        accent_hover="#a6c8ff",
        on_accent="#11111b",
        fg="#cdd6f4",
        text_muted="#9399b2",
        text_disabled="#585b70",
        success="#a6e3a1",
        warning="#f9e2af",
        error="#f38ba8",
        info="#89dceb",
    ),
    "Nord": ThemePalette(
        name="Nord",
        surface_dim="#242933",
        bg="#2e3440",
        surface="#3b4252",
        elevated="#434c5e",
        border="#4c566a",
        border_strong="#5e6a82",
        accent="#88c0d0",
        accent_hover="#a3d0dd",
        on_accent="#2e3440",
        fg="#eceff4",
        text_muted="#b9c1d0",
        text_disabled="#6b7488",
        success="#a3be8c",
        warning="#ebcb8b",
        error="#bf616a",
        info="#81a1c1",
    ),
    "Latte": ThemePalette(
        name="Latte",
        surface_dim="#e6e9ef",
        bg="#eff1f5",
        surface="#f7f9fc",
        elevated="#ffffff",
        border="#ccd0da",
        border_strong="#acb0be",
        accent="#1e66f5",
        accent_hover="#3d7bff",
        on_accent="#ffffff",
        fg="#4c4f69",
        text_muted="#6c6f85",
        text_disabled="#9ca0b0",
        success="#40a02b",
        warning="#df8e1d",
        error="#d20f39",
        info="#209fb5",
    ),
}
