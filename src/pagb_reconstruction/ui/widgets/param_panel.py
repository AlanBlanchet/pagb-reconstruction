from typing import Literal, get_args, get_origin

from PySide6.QtCore import (
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pagb_reconstruction.core.reconstruction import ReconstructionConfig
from pagb_reconstruction.ui.model_widget import _unwrap_optional
from pagb_reconstruction.ui.theme import active_theme, icon

_PRESETS = {
    "Default": ReconstructionConfig(),
    "Fine": ReconstructionConfig(
        threshold_deg=1.5,
        tolerance_deg=1.5,
        grain_threshold_deg=3.0,
        min_grain_size=3,
        merge_similar_deg=5.0,
        inflation_power=1.8,
    ),
    "Coarse": ReconstructionConfig(
        threshold_deg=4.0,
        tolerance_deg=4.0,
        grain_threshold_deg=8.0,
        min_grain_size=10,
        merge_similar_deg=10.0,
        inflation_power=1.4,
    ),
    # Bainite has weaker variant selection than martensite (Wang et al. 2025):
    # laths spread wider around the ideal OR variants, so grouping tolerances are
    # looser and clustering coarser (lower inflation). NW/KS both work for bainite
    # (Taylor et al. 2024). min_parent_size prunes sub-µm noise islands; real prior
    # austenite is 15–50 µm.
    "Bainite": ReconstructionConfig(
        threshold_deg=3.5,
        tolerance_deg=3.0,
        grain_threshold_deg=5.0,
        min_grain_size=5,
        merge_similar_deg=8.0,
        inflation_power=1.3,
        min_parent_size_um=5.0,
    ),
}

_FIELD_GROUPS = {
    "Grain Detection": ["fill_nonindexed", "grain_threshold_deg", "min_grain_size"],
    "Clustering": [
        "algorithm",
        "or_type",
        "optimize_or",
        "threshold_deg",
        "tolerance_deg",
        "inflation_power",
        "min_cluster_size",
    ],
    "Post-processing": [
        "revert_threshold_deg",
        "merge_similar_deg",
        "merge_inclusions_max_size",
        "min_parent_size_um",
        "n_vote_iterations",
    ],
}

_GROUP_ICONS = {
    "Grain Detection": "grain",
    "Clustering": "layers",
    "Post-processing": "params",
}


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False):
        super().__init__()
        self._checked = checked
        self.setFixedSize(40, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        self._checked = val
        self.update()

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, event):
        p = active_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_color = QColor(p.accent if self._checked else p.border)
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 2, 40, 16, 8, 8)
        knob_x = 22 if self._checked else 2
        painter.setBrush(QColor(p.fg))
        painter.drawEllipse(knob_x, 2, 16, 16)
        painter.end()


class SliderSpinCombo(QWidget):
    value_changed = Signal(float)

    def __init__(
        self,
        min_val: float,
        max_val: float,
        value: float,
        decimals: int = 2,
        is_int: bool = False,
    ):
        super().__init__()
        self._decimals = decimals
        self._is_int = is_int
        self._scale = 1 if is_int else 10**decimals

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(int(min_val * self._scale))
        self._slider.setMaximum(int(max_val * self._scale))
        self._slider.setValue(int(value * self._scale))
        layout.addWidget(self._slider, 1)

        if is_int:
            self._spin = QSpinBox()
            self._spin.setMinimum(int(min_val))
            self._spin.setMaximum(int(max_val))
            self._spin.setValue(int(value))
        else:
            self._spin = QDoubleSpinBox()
            self._spin.setDecimals(decimals)
            self._spin.setMinimum(min_val)
            self._spin.setMaximum(max_val)
            self._spin.setValue(value)
        self._spin.setFixedWidth(70)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._slider_moved)
        if is_int:
            self._spin.valueChanged.connect(self._spin_changed_int)
        else:
            self._spin.valueChanged.connect(self._spin_changed_float)

    def _slider_moved(self, val: int):
        real = val if self._is_int else val / self._scale
        self._spin.blockSignals(True)
        self._spin.setValue(real)
        self._spin.blockSignals(False)
        self.value_changed.emit(float(real))

    def _spin_changed_float(self, val: float):
        self._slider.blockSignals(True)
        self._slider.setValue(int(val * self._scale))
        self._slider.blockSignals(False)
        self.value_changed.emit(val)

    def _spin_changed_int(self, val: int):
        self._slider.blockSignals(True)
        self._slider.setValue(val)
        self._slider.blockSignals(False)
        self.value_changed.emit(float(val))

    def value(self) -> float:
        return self._spin.value()


class SegmentedControl(QWidget):
    selection_changed = Signal(str)

    def __init__(self, options: list[str]):
        super().__init__()
        self._buttons: list[QLabel] = []
        self._active_index = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for i, opt in enumerate(options):
            btn = QLabel(opt)
            btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.mousePressEvent = lambda e, idx=i: self._select(idx)
            self._buttons.append(btn)
            layout.addWidget(btn)

        self._apply_styles()

    def _select(self, index: int):
        self._active_index = index
        self._apply_styles()
        self.selection_changed.emit(self._buttons[index].text())

    def _apply_styles(self):
        for i, btn in enumerate(self._buttons):
            btn.setProperty("active", "true" if i == self._active_index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def current_text(self) -> str | None:
        if self._active_index < 0:
            return None
        return self._buttons[self._active_index].text()

    def set_current(self, text: str | None):
        """Programmatic selection; ``None`` deselects every segment (the shown
        values match no preset). Does not re-emit selection_changed."""
        self._active_index = next(
            (i for i, b in enumerate(self._buttons) if b.text() == text), -1
        )
        self._apply_styles()


class CollapsibleCard(QWidget):
    def __init__(self, title: str, icon_name: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded = True
        p = active_theme()

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("cardFrame")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(10, 6, 10, 6)
        frame_layout.setSpacing(4)

        header = QWidget()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        if icon_name:
            _ic = QLabel()
            _ic.setPixmap(icon(icon_name, color=p.text_muted).pixmap(14, 14))
            header_layout.addWidget(_ic)
        self._title_label = QLabel(title)
        self._title_label.setObjectName("cardTitle")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        self._chevron = QLabel()
        self._chevron.setPixmap(icon("chevron_down", color=p.text_muted).pixmap(12, 12))
        header_layout.addWidget(self._chevron)
        header.mousePressEvent = lambda e: self.set_expanded(not self._expanded)
        frame_layout.addWidget(header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 4, 0, 4)
        self._content_layout.setSpacing(4)
        frame_layout.addWidget(self._content)

        self._main_layout.addWidget(self._frame)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._content.setVisible(expanded)
        _name = "chevron_down" if expanded else "chevron_right"
        self._chevron.setPixmap(icon(_name, color=active_theme().text_muted).pixmap(12, 12))


class ParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._config = ReconstructionConfig()
        self._field_widgets: dict[str, QWidget] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._preset_control = SegmentedControl(list(_PRESETS.keys()))
        self._preset_control.selection_changed.connect(self._apply_preset)
        layout.addWidget(self._preset_control)

        self._reset_btn = QPushButton("Restore defaults")
        self._reset_btn.setToolTip("Reset every parameter to its default value")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self._reset_btn)

        self._cards_container = QVBoxLayout()
        self._cards_container.setSpacing(6)
        layout.addLayout(self._cards_container)
        layout.addStretch()

        self._build_cards()

    def _build_cards(self):
        while self._cards_container.count():
            item = self._cards_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_widgets.clear()

        for group_name, fields in _FIELD_GROUPS.items():
            card = CollapsibleCard(group_name, _GROUP_ICONS.get(group_name))

            for field_name in fields:
                field_info = ReconstructionConfig.model_fields.get(field_name)
                if field_info is None:
                    continue
                value = getattr(self._config, field_name)
                annotation = field_info.annotation
                label_text = field_info.title or field_name.replace("_", " ").title()

                row = QHBoxLayout()
                row.setSpacing(4)
                lbl = QLabel(label_text)
                lbl.setStyleSheet("font-size: 11px;")
                lbl.setMinimumWidth(120)
                row.addWidget(lbl)

                widget = self._make_field_widget(
                    field_name, annotation, field_info, value
                )
                if widget:
                    row.addWidget(widget, 1)
                    self._field_widgets[field_name] = widget
                    if field_info.description:
                        widget.setToolTip(field_info.description)

                row_widget = QWidget()
                row_widget.setLayout(row)
                card.content_layout().addWidget(row_widget)

            self._cards_container.addWidget(card)

    def _make_field_widget(
        self, name: str, annotation, field_info, value
    ) -> QWidget | None:
        annotation = _unwrap_optional(annotation)

        if annotation is bool:
            w = ToggleSwitch(bool(value))
            return w
        if annotation is int:
            min_val, max_val = 1, 200
            for meta in field_info.metadata:
                if hasattr(meta, "ge") and meta.ge is not None:
                    min_val = meta.ge
                if hasattr(meta, "le") and meta.le is not None:
                    max_val = meta.le
            return SliderSpinCombo(min_val, max_val, int(value or 0), is_int=True)
        if annotation is float:
            min_val, max_val = 0.0, 20.0
            for meta in field_info.metadata:
                if hasattr(meta, "ge") and meta.ge is not None:
                    min_val = meta.ge
                if hasattr(meta, "le") and meta.le is not None:
                    max_val = meta.le
            return SliderSpinCombo(min_val, max_val, float(value or 0.0), decimals=2)
        if get_origin(annotation) is Literal:
            w = QComboBox()
            for opt in get_args(annotation):
                w.addItem(str(opt), opt)
            if value:
                w.setCurrentText(str(value))
            return w
        if annotation is str:
            return QLineEdit(str(value or ""))
        return None

    def reset_to_defaults(self):
        """Restore every parameter to its default (issue #11)."""
        self.set_config(ReconstructionConfig())

    def _apply_preset(self, name: str):
        preset = _PRESETS.get(name)
        if preset is None:
            return
        self._config = preset
        self._build_cards()

    def set_config(self, config: ReconstructionConfig):
        """Adopt a full configuration (e.g. the winner of a comparison run) and
        sync the preset tabs — highlight a matching preset, deselect otherwise
        (a stale highlight invites a click that silently resets the values)."""
        self._config = config
        match = next(
            (
                name
                for name, preset in _PRESETS.items()
                if preset.model_dump() == config.model_dump()
            ),
            None,
        )
        self._preset_control.set_current(match)
        self._build_cards()

    def get_config(self) -> ReconstructionConfig:
        model_cls = type(self._config)
        data: dict[str, object] = {}
        for name, widget in self._field_widgets.items():
            data[name] = self._read_value(widget)
        for name in model_cls.model_fields:
            if name not in data:
                data[name] = getattr(self._config, name)
        return model_cls(**data)

    def _read_value(self, widget: QWidget):
        if isinstance(widget, ToggleSwitch):
            return widget.isChecked()
        if isinstance(widget, SliderSpinCombo):
            return widget.value()
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QLineEdit):
            return widget.text()
        return None
