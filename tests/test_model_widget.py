"""The generic pydantic-model form widget.

A form built from a Displayable must announce edits so a panel can react — e.g.
mark a shown measurement stale when its settings change (Eloïse #15 finding B:
changing "Test lines" left the old number displayed with no cue it was stale).
"""


def test_form_emits_changed_when_a_field_is_edited(qtbot):
    from pagb_reconstruction.core.grain_metrics import GrainMetrics

    w = GrainMetrics(n_lines=10).to_widget()
    qtbot.addWidget(w)
    fired = []
    w.changed.connect(lambda: fired.append(True))
    w._field_widgets["n_lines"].setValue(25)
    assert fired, "the form must emit `changed` when a field is edited"


def test_form_emits_changed_on_a_combo_choice(qtbot):
    from pagb_reconstruction.core.grain_metrics import GrainMetrics

    w = GrainMetrics(method="intercept").to_widget()
    qtbot.addWidget(w)
    fired = []
    w.changed.connect(lambda: fired.append(True))
    combo = w._field_widgets["method"]
    combo.setCurrentText("area")
    assert fired, "changing a Literal combo must emit `changed`"


# ── F2: `changed` must fire for EVERY field kind, not just the 4 native ones ──


def test_form_relays_nested_model_edits(qtbot):
    from pydantic import Field

    from pagb_reconstruction.core.base import Displayable
    from pagb_reconstruction.ui.model_widget import ModelFormWidget

    class Inner(Displayable):
        n: int = Field(default=1)

    class Outer(Displayable):
        inner: Inner = Field(default_factory=Inner)

    w = Outer().to_widget()
    qtbot.addWidget(w)
    fired = []
    w.changed.connect(lambda: fired.append(True))
    inner_form = w._field_widgets["inner"].findChild(ModelFormWidget)
    inner_form._field_widgets["n"].setValue(9)
    assert fired, "editing a nested-model field must bubble up as `changed`"


def test_form_relays_color_button_change(qtbot):
    from unittest.mock import patch

    from PySide6.QtGui import QColor
    from pydantic import Field

    from pagb_reconstruction.core.base import Displayable

    class HasColor(Displayable):
        line_color: str = Field(default="#FF0000")

    w = HasColor().to_widget()
    qtbot.addWidget(w)
    fired = []
    w.changed.connect(lambda: fired.append(True))
    with patch(
        "pagb_reconstruction.ui.model_widget.QColorDialog.getColor",
        return_value=QColor("#00FF00"),
    ):
        w._field_widgets["line_color"].click()
    assert fired, "picking a colour must emit `changed`"
