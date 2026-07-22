

def test_checked_toolbutton_is_unmistakably_armed():
    """A toggled-on tool must read as ARMED at a glance, not as a faint tint.

    The Line Profile toggle was mis-armed twice by a tester who was explicitly
    watching for it, because checked state was a 24% accent mix that reads as
    hover. An armed mode that silently disarms makes the tool look broken.
    """
    from pagb_reconstruction.ui.theme.engine import _compile
    from pagb_reconstruction.ui.theme.palette import THEMES

    import re

    css = _compile(next(iter(THEMES.values())))
    block = re.search(r"QToolButton:checked\s*\{([^}]*)\}", css)
    assert block, "no checked-state rule for QToolButton"
    body = block.group(1)

    # Assert the BORDER, not the background: qdarktheme's additional_qss wins the
    # background cascade for this selector, so a background assertion here passes
    # while the pixels ignore it — a test of our model, not of the mechanism.
    accent = THEMES[next(iter(THEMES))].accent.lstrip("#").lower()
    border = re.search(r"border[^;]*:", body)
    assert border, f"checked state needs a border cue, got: {body}"
    assert accent in body.lower().replace("#", ""), (
        f"checked border must use the accent colour so armed reads at a glance: {body}"
    )
    assert "mix(" not in body, "a mixed/washed cue reads as hover, not as armed"
