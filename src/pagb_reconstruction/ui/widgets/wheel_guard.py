"""Stop spin boxes and combos from swallowing the wheel they are scrolled past.

Inside a scrolling panel, Qt gives a wheel event to whatever widget is under the
cursor. A QSpinBox or QComboBox accepts it unconditionally, so rolling the wheel
over one produces a silent dead-zone: the panel does not scroll and — because the
widget is unfocused and the user was not aiming at it — the value change is
either unwanted or invisible. Measured live in the Statistics header, where the
wheel stalled the instant the cursor crossed the Method combo and resumed on
blank space 500px away.

The rule: a control consumes the wheel only when it has focus, i.e. when the user
deliberately selected it. Otherwise the event propagates to the scroll area,
which is what the user meant.
"""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QWidget

_WHEEL_HUNGRY = (QAbstractSpinBox, QComboBox)


class _WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            return True  # consumed here, so the control never sees it
        return False


def install_wheel_guard(widget: QWidget) -> None:
    """Guard ``widget`` if it is wheel-hungry, and every such descendant."""
    guard = _WheelGuard(widget)
    targets: list[QWidget] = [widget] if isinstance(widget, _WHEEL_HUNGRY) else []
    targets += widget.findChildren(QAbstractSpinBox)
    targets += widget.findChildren(QComboBox)
    for target in targets:
        target.installEventFilter(guard)
        # Keep a reference: the filter dies with its parent, not with the loop.
        target._wheel_guard = guard  # noqa: SLF001
