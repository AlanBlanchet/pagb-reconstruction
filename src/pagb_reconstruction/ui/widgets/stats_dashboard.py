"""Statistics — a plot BROWSER, not a row of squished charts.

The old dashboard crammed four charts into one short, wide grid row; the pole
figure and misorientation spectrum lived in their own tiny separate docks. Alan:
"the angular plot in its own panel is small and useless… stop making things all
squishy and tight… we could have many other different plots."

So this is a browser: a grouped selector on the left, ONE large focused plot on
the right that owns the whole panel. Plots come from the ``stat_plots`` catalog,
so "many other plots" is a one-line catalog entry, and none of them wheel-zoom on
hover (the "weird per-plot scroll").
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.ui.widgets.stat_plots import CATALOG, PlotContext

_UNSET = object()


class StatCard(QWidget):
    def __init__(self, label: str, value: str = "-"):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(64)
        self.setMinimumWidth(110)
        self.setMaximumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setObjectName("statLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._value = QLabel(value)
        self._value.setObjectName("statValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

    def set_value(self, text: str):
        self._value.setText(text)


class StatsDashboard(QWidget):
    """Grouped plot selector (left) + one large focused plot (right)."""

    def __init__(self):
        super().__init__()
        self._ctx = PlotContext()
        self._built: dict[str, QWidget] = {}
        self._current_key: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        self._selector = QListWidget()
        self._selector.setObjectName("plotSelector")
        self._selector.setFixedWidth(176)
        self._selector.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._selector.currentItemChanged.connect(self._on_select)
        outer.addWidget(self._selector)

        self._host = QStackedWidget()
        self._placeholder = QLabel("Run a reconstruction to see statistics.")
        self._placeholder.setObjectName("plotPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._host.addWidget(self._placeholder)
        outer.addWidget(self._host, 1)

        self._populate_selector()

    # ── context ────────────────────────────────────────────────────
    def set_context(self, *, result=_UNSET, ebsd_map=_UNSET, or_type=_UNSET):
        """Merge in whatever changed (loaded map, chosen OR, finished result) and
        refresh the plot list; unspecified fields keep their current value."""
        r = self._ctx.result if result is _UNSET else result
        e = self._ctx.ebsd_map if ebsd_map is _UNSET else ebsd_map
        o = self._ctx.or_type if or_type is _UNSET else or_type
        self._ctx = PlotContext(result=r, ebsd_map=e, or_type=o)
        self._clear_built()
        self._populate_selector()

    def update_stats(self, result, ebsd_map=None, or_type: str = "", elapsed: float = 0.0):
        # Retained call shape for the reconstruction-done path.
        self.set_context(result=result, ebsd_map=ebsd_map, or_type=or_type)

    def _clear_built(self):
        while self._host.count() > 1:
            w = self._host.widget(1)
            self._host.removeWidget(w)
            w.deleteLater()
        self._built.clear()

    # ── selector ───────────────────────────────────────────────────
    def _available(self):
        # A plot whose data probe raises on this context is simply not offered,
        # never a crash — the browser must survive partial / stub contexts.
        out = []
        for entry in CATALOG:
            try:
                if entry.available(self._ctx):
                    out.append(entry)
            except Exception:  # noqa: BLE001 — unavailable, not fatal
                continue
        return out

    def _populate_selector(self):
        self._selector.blockSignals(True)
        self._selector.clear()
        available = self._available()
        keys = [e.key for e in available]
        target = self._current_key if self._current_key in keys else (
            keys[0] if keys else None
        )
        by_cat: dict[str, list] = {}
        for e in available:
            by_cat.setdefault(e.category, []).append(e)
        for category, entries in by_cat.items():
            header = QListWidgetItem(category.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)  # a non-selectable group label
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self._selector.addItem(header)
            for e in entries:
                item = QListWidgetItem(e.title)
                item.setData(Qt.ItemDataRole.UserRole, e.key)
                self._selector.addItem(item)
        self._selector.blockSignals(False)
        self._select_key(target)

    def _select_key(self, key: str | None):
        if key is None:
            self._current_key = None
            self._host.setCurrentWidget(self._placeholder)
            return
        for i in range(self._selector.count()):
            item = self._selector.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self._selector.setCurrentItem(item)  # fires _on_select → _show
                return

    def _on_select(self, current: QListWidgetItem | None, _previous):
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key:
            self._show(key)

    def _show(self, key: str):
        self._current_key = key
        if key not in self._built:
            entry = next((e for e in CATALOG if e.key == key), None)
            if entry is None:
                self._host.setCurrentWidget(self._placeholder)
                return
            widget = entry.build(self._ctx)
            self._built[key] = widget
            self._host.addWidget(widget)
        self._host.setCurrentWidget(self._built[key])
