"""Every semantic icon must resolve to a real (non-null) themed QIcon."""

from PySide6.QtGui import QIcon


def test_every_registered_icon_resolves(qapp):
    from pagb_reconstruction.ui.theme.icons import _REGISTRY, icon

    for name in _REGISTRY:
        ic = icon(name)
        assert isinstance(ic, QIcon) and not ic.isNull(), name


def test_unknown_icon_is_null(qapp):
    from pagb_reconstruction.ui.theme.icons import icon

    assert icon("does-not-exist").isNull()
