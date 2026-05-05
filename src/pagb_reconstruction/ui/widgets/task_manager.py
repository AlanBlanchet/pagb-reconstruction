from typing import Literal

from PySide6.QtCore import QElapsedTimer, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.ui.theme import active_theme


class TaskItem(QWidget):
    cancel_requested = Signal(str)

    def __init__(self, task_id: str, name: str):
        super().__init__()
        self._task_id = task_id
        self._status = "running"
        self._timer = QElapsedTimer()
        self._timer.start()
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._update_time)
        self._tick_timer.start(1000)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        self._icon = QLabel("\u25cf")
        self._icon.setFixedWidth(14)
        layout.addWidget(self._icon)

        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(1)
        self._name_label = QLabel(name)
        self._name_label.setStyleSheet("font-size: 11px;")
        mid.addWidget(self._name_label)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        mid.addWidget(self._progress)
        layout.addLayout(mid, 1)

        self._time_label = QLabel("0s")
        self._time_label.setFixedWidth(40)
        self._time_label.setStyleSheet("font-size: 10px;")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._time_label)

        self._cancel_btn = QPushButton("\u2715")
        self._cancel_btn.setFixedSize(18, 18)
        self._cancel_btn.setStyleSheet("border: none; font-size: 11px; padding: 0;")
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._task_id))
        layout.addWidget(self._cancel_btn)

        self._apply_style()

    def _apply_style(self):
        p = active_theme()
        colors = {"running": p.accent, "done": p.success, "error": p.error, "cancelled": p.warning}
        color = colors.get(self._status, p.accent)
        self._icon.setStyleSheet(f"color: {color}; font-size: 12px;")

    def set_progress(self, pct: float):
        if pct < 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(pct))

    def set_status(self, status: Literal["running", "done", "error", "cancelled"]):
        self._status = status
        icons = {"running": "\u25cf", "done": "\u2713", "error": "\u2717", "cancelled": "\u2014"}
        self._icon.setText(icons.get(status, "\u25cf"))
        self._apply_style()
        if status != "running":
            self._tick_timer.stop()
            self._cancel_btn.setVisible(False)

    def _update_time(self):
        elapsed = self._timer.elapsed() // 1000
        if elapsed < 60:
            self._time_label.setText(f"{elapsed}s")
        else:
            self._time_label.setText(f"{elapsed // 60}m{elapsed % 60:02d}s")


class TaskManager(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tasks: dict[str, TaskItem] = {}
        self._dismiss_timers: dict[str, QTimer] = {}
        self.setFixedWidth(300)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(2)

        self._title = QLabel("Tasks")
        self._title.setStyleSheet("font-size: 10px; font-weight: bold;")
        self._layout.addWidget(self._title)
        self._layout.addStretch()

        self._update_visibility()
        self._update_style()

    def _update_style(self):
        p = active_theme()
        r, g, b = int(p.surface_dim[1:3], 16), int(p.surface_dim[3:5], 16), int(p.surface_dim[5:7], 16)
        self.setStyleSheet(
            f"TaskManager {{ background: rgba({r}, {g}, {b}, 230); "
            f"border-radius: 8px; border: 1px solid {p.border}; }}"
        )
        self._title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {p.text_muted};")

    def submit(self, task_id: str, name: str) -> TaskItem:
        if task_id in self._tasks:
            self._dismiss(task_id)
        item = TaskItem(task_id, name)
        item.cancel_requested.connect(self.cancel)
        self._tasks[task_id] = item
        self._layout.insertWidget(self._layout.count() - 1, item)
        self._update_visibility()
        return item

    def update_progress(self, task_id: str, pct: float):
        item = self._tasks.get(task_id)
        if item:
            item.set_progress(pct)

    def complete(self, task_id: str, status: Literal["running", "done", "error", "cancelled"] = "done"):
        item = self._tasks.get(task_id)
        if item:
            item.set_status(status)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._dismiss(task_id))
            timer.start(3000)
            self._dismiss_timers[task_id] = timer

    def cancel(self, task_id: str):
        self.complete(task_id, "cancelled")

    def _dismiss(self, task_id: str):
        item = self._tasks.pop(task_id, None)
        if item:
            self._layout.removeWidget(item)
            item.deleteLater()
        self._dismiss_timers.pop(task_id, None)
        self._update_visibility()

    def _update_visibility(self):
        has_tasks = len(self._tasks) > 0
        self.setVisible(has_tasks)

    def reposition(self, parent_width: int, parent_height: int):
        x = parent_width - self.width() - 12
        self.move(x, 12)
