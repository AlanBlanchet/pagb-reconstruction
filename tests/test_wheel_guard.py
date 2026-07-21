"""A wheel rolled over a spin box or combo must scroll the panel, not stall.

Inside a scrolling panel Qt hands the wheel to the widget under the cursor, and
a QSpinBox/QComboBox accepts it unconditionally — producing a silent dead-zone
where the panel will not scroll and no value visibly changes. Measured live in
the Statistics header: scrolling stalled the instant the cursor crossed the
Method combo, with no feedback, and resumed on blank space 500px away.
"""


def test_spinboxes_ignore_wheel_until_focused(qtbot):
    """A wheel over a spin/combo inside a scroll area is swallowed: it neither
    scrolls the panel nor changes the value, with no feedback. Measured live as
    a dead-zone the user cannot diagnose. Wheel is only for a focused control.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QSpinBox

    from pagb_reconstruction.ui.widgets.wheel_guard import install_wheel_guard

    box = QSpinBox()
    qtbot.addWidget(box)
    box.setRange(0, 100)
    box.setValue(50)
    install_wheel_guard(box)

    event = QWheelEvent(
        QPoint(5, 5), QPoint(5, 5), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    box.clearFocus()
    QApplication.sendEvent(box, event)
    assert box.value() == 50, "unfocused spinbox must not consume the wheel"
    assert not event.isAccepted(), "unfocused wheel must propagate to the scroll area"

    # ...and a focused control still works normally, or the guard would be a bug
    box.show()
    box.activateWindow()
    box.setFocus()
    if not box.hasFocus():  # offscreen platform may refuse focus
        return
    focused = QWheelEvent(
        QPoint(5, 5), QPoint(5, 5), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(box, focused)
    assert box.value() == 51, "a focused spinbox must still respond to the wheel"
