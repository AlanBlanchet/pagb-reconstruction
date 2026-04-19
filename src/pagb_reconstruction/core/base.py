from collections.abc import Callable
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict

from pagb_reconstruction.core.crystal import (
    CrystalFamily,
    LatticeParams,
    _POINT_GROUP_TO_SPACE_GROUP,
)


class Displayable(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    _ui_title: ClassVar[str] = ""

    def to_widget(self, parent: Any = None):
        from pagb_reconstruction.ui.model_widget import ModelFormWidget

        return ModelFormWidget(self, parent=parent)

    def to_dict_display(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, field in type(self).model_fields.items():
            val = getattr(self, name)
            if isinstance(val, np.ndarray):
                result[name] = f"ndarray{val.shape}"
            elif isinstance(val, BaseModel):
                result[name] = str(val.model_dump())
            else:
                result[name] = str(val)
        return result


class SpatialRegion(Displayable):
    pixel_indices: np.ndarray

    def mask(self, shape: tuple[int, ...]) -> np.ndarray:
        total = 1
        for s in shape:
            total *= s
        m = np.zeros(total, dtype=bool)
        m[self.pixel_indices] = True
        return m.reshape(shape)

    def highlight_on(self, viewer: Any, color: str = "#FFFF00"):
        from pagb_reconstruction.ui.model_widget import highlight_region

        highlight_region(viewer, self, color)


class CrystallographicEntity(Displayable):
    family: CrystalFamily
    point_group: str
    lattice: LatticeParams

    @property
    def symmetry(self):
        from orix.quaternion.symmetry import get_point_group

        sg_num = _POINT_GROUP_TO_SPACE_GROUP.get(self.point_group, 225)
        return get_point_group(sg_num)

    @property
    def n_symmetry_ops(self) -> int:
        return self.symmetry.size


_MAP_PROPERTY_ATTR = "__map_property__"


class _MapPropertyMeta:
    __slots__ = ("name", "requires_result")

    def __init__(self, name: str, requires_result: bool):
        self.name = name
        self.requires_result = requires_result


def map_property(name: str, requires_result: bool = False) -> Callable:
    def decorator(fn: Callable) -> Callable:
        setattr(fn, _MAP_PROPERTY_ATTR, _MapPropertyMeta(name, requires_result))
        return fn

    return decorator


class SpatialMap(Displayable):
    @classmethod
    def registered_map_properties(cls) -> list[_MapPropertyMeta]:
        props: list[_MapPropertyMeta] = []
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if attr is None:
                continue
            meta = getattr(attr, _MAP_PROPERTY_ATTR, None)
            if meta is not None:
                props.append(meta)
        return props

    def compute_map_property(self, name: str, **kwargs: Any) -> np.ndarray:
        for attr_name in dir(self):
            attr = getattr(type(self), attr_name, None)
            if attr is None:
                continue
            meta = getattr(attr, _MAP_PROPERTY_ATTR, None)
            if meta is not None and meta.name == name:
                return getattr(self, attr_name)(**kwargs)
        msg = f"Unknown map property: {name}"
        raise KeyError(msg)
