import types
from enum import Enum
from typing import Literal, get_args, get_origin

import numpy as np
from pydantic import BaseModel
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ModelFormWidget(QWidget):

    def __init__(self, model: BaseModel, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = model
        self._field_widgets: dict[str, QWidget] = {}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for name, field_info in type(self._model).model_fields.items():
            annotation = field_info.annotation
            value = getattr(self._model, name)
            if annotation is np.ndarray or (
                isinstance(annotation, type) and issubclass(annotation, np.ndarray)
            ):
                continue
            widget = self._make_widget(name, annotation, field_info, value)
            if widget is None:
                continue
            label = field_info.title or name.replace("_", " ").title()
            form.addRow(f"{label}:", widget)
            self._field_widgets[name] = widget
        layout.addLayout(form)

    def _make_widget(self, name: str, annotation, info, value) -> QWidget | None:
        annotation = _unwrap_optional(annotation)

        if annotation is bool:
            w = QCheckBox()
            w.setChecked(bool(value))
            return w
        if annotation is int:
            w = QSpinBox()
            _apply_constraints(w, info)
            w.setValue(int(value or 0))
            return w
        if annotation is float:
            w = QDoubleSpinBox()
            w.setDecimals(3)
            _apply_constraints(w, info)
            w.setValue(float(value or 0.0))
            return w
        if annotation is str:
            if "color" in name.lower():
                return _make_color_button(str(value or "#FF0000"))
            return QLineEdit(str(value or ""))
        if get_origin(annotation) is Literal:
            w = QComboBox()
            for opt in get_args(annotation):
                w.addItem(str(opt), opt)
            if value:
                w.setCurrentText(str(value))
            return w
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            w = QComboBox()
            for member in annotation:
                w.addItem(member.name, member)
            if value:
                w.setCurrentText(value.name if isinstance(value, Enum) else str(value))
            return w
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if isinstance(value, BaseModel):
                group = QGroupBox(name.replace("_", " ").title())
                inner = ModelFormWidget(value)
                group_layout = QVBoxLayout(group)
                group_layout.addWidget(inner)
                return group
        return None

    def to_model(self):
        model_cls = type(self._model)
        data: dict[str, object] = {}
        for name, widget in self._field_widgets.items():
            data[name] = _read_widget_value(widget)
        for name in model_cls.model_fields:
            if name not in data:
                data[name] = getattr(self._model, name)
        return model_cls(**data)


def _unwrap_optional(annotation):
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is types.UnionType or (origin and str(origin) == "typing.Union"):
        real_args = [a for a in args if a is not type(None)]
        if len(real_args) == 1:
            return real_args[0]
    return annotation


def _apply_constraints(spinbox: QSpinBox | QDoubleSpinBox, field_info):
    for meta in field_info.metadata:
        if hasattr(meta, "ge") and meta.ge is not None:
            spinbox.setMinimum(meta.ge)
        if hasattr(meta, "le") and meta.le is not None:
            spinbox.setMaximum(meta.le)


def _read_widget_value(widget: QWidget):
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QComboBox):
        return widget.currentData()
    if isinstance(widget, QPushButton):
        return widget.property("color_value") or "#FF0000"
    if isinstance(widget, QGroupBox):
        inner = widget.findChild(ModelFormWidget)
        if inner:
            return inner.to_model()
    return None


def _make_color_button(color_str: str) -> QPushButton:
    btn = QPushButton()
    btn.setProperty("color_value", color_str)
    btn.setStyleSheet(
        f"background-color: {color_str}; min-width: 60px; min-height: 20px;"
    )

    def pick():
        c = QColorDialog.getColor()
        if c.isValid():
            btn.setProperty("color_value", c.name())
            btn.setStyleSheet(
                f"background-color: {c.name()}; min-width: 60px; min-height: 20px;"
            )

    btn.clicked.connect(pick)
    return btn


def highlight_region(viewer, spatial_region, color: str = "#FFFF00"):
    pass
