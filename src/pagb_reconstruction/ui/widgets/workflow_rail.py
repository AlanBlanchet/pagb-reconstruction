"""The analysis workflow made visible: Load → Phases → OR → Params → Run → Review.

The tabbed layout implies this order only by tab position; nothing tells a
first-time user what to do first, and every stage's controls are on screen at
every moment. The rail names the stages in our own icon language and clicking
one surfaces the panels that stage needs — the map never moves. It is additive:
every existing tab keeps working, so each stage's routing is verifiable on its
own rather than as a big-bang rework.

Structure borrowed from workflow-driven analysis tools; the look is deliberately
ours (SCSS theme + Phosphor icons) — the reference products' own styling is not
a goal (decisions.md 2026-07-22).
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

from pagb_reconstruction.ui.theme import icon


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    icon: str
    tip: str


_STAGES = (
    Stage("load", "Load", "open", "Open an EBSD map (.ctf / .ang / .h5)"),
    Stage("phases", "Phases", "phases", "Check the phases the file declares"),
    Stage("or", "OR", "or", "Choose the orientation relationship"),
    Stage("params", "Params", "params", "Tune detection and clustering"),
    Stage("run", "Run", "run", "Reconstruct the parent grains"),
    Stage("review", "Review", "review", "Inspect and correct the worst fits"),
)


class WorkflowRail(QWidget):
    """Vertical stage list; exactly one stage reads as current."""

    stage_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("workflowRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        for stage in _STAGES:
            btn = QToolButton()
            btn.setObjectName("railStage")
            btn.setText(stage.label)
            try:
                btn.setIcon(icon(stage.icon))
            except Exception:  # noqa: BLE001 — a missing glyph must not kill the rail
                pass
            btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            )
            btn.setCheckable(True)
            btn.setToolTip(stage.tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=stage.key: self._on_click(k))
            self._group.addButton(btn)
            self._buttons[stage.key] = btn
            layout.addWidget(btn)
        layout.addStretch()

    def stages(self) -> tuple[Stage, ...]:
        return _STAGES

    def select(self, key: str) -> None:
        """Programmatic selection — same path as a click, one signal."""
        btn = self._buttons.get(key)
        if btn is None:
            return
        btn.setChecked(True)
        self.stage_selected.emit(key)

    def is_current(self, key: str) -> bool:
        btn = self._buttons.get(key)
        return btn is not None and btn.isChecked()

    def _on_click(self, key: str) -> None:
        self.stage_selected.emit(key)
