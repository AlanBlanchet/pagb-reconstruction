from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.manual_edit import worst_fit_parents


class ParentReviewPanel(QWidget):
    """Review reconstructed parents worst-misfit first, and reattach the bad ones.

    Automatic reconstruction gets most parents right and a few wrong; this is
    where the operator finds the wrong ones (they sort to the top) and says which
    parent they should belong to instead.
    """

    parent_selected = Signal(int)
    reassign_requested = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        hint = QLabel("Parents with the worst misfit first — select one to locate it.")
        hint.setWordWrap(True)
        hint.setObjectName("infoHint")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Parent", "Pixels", "Mean fit (°)"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table, 1)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Reattach to parent:"))
        self._target_spin = QSpinBox()
        self._target_spin.setRange(0, 999_999)
        action_row.addWidget(self._target_spin)
        self._reassign_btn = QPushButton("Reattach")
        self._reassign_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reassign_btn.setEnabled(False)
        self._reassign_btn.clicked.connect(self._on_reassign)
        action_row.addWidget(self._reassign_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

    def set_result(self, result) -> None:
        """Populate from a reconstruction result (None clears the panel)."""
        self._rows = [] if result is None else worst_fit_parents(result, limit=200)
        self._table.setRowCount(len(self._rows))
        for row, info in enumerate(self._rows):
            for col, text in enumerate(
                (str(info.parent_id), str(info.n_pixels), f"{info.mean_fit_deg:.2f}")
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)
        self._reassign_btn.setEnabled(False)

    def selected_parent(self) -> int | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row].parent_id
        return None

    def _on_selection(self):
        pid = self.selected_parent()
        self._reassign_btn.setEnabled(pid is not None)
        if pid is not None:
            self.parent_selected.emit(pid)

    def _on_reassign(self):
        pid = self.selected_parent()
        if pid is None:
            return
        target = int(self._target_spin.value())
        if target == pid:
            return
        self.reassign_requested.emit(pid, target)
