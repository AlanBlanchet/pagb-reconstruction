import functools
import logging
from collections.abc import Callable
from typing import Any, ClassVar, Literal

import numpy as np
from orix.quaternion.symmetry import get_point_group
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
        sg_num = _POINT_GROUP_TO_SPACE_GROUP.get(self.point_group, 225)
        return get_point_group(sg_num)

    @property
    def n_symmetry_ops(self) -> int:
        return self.symmetry.size


_MAP_PROPERTY_ATTR = "__map_property__"

MapDtype = Literal["scalar", "rgb", "discrete"]


class _MapPropertyMeta:
    __slots__ = (
        "name",
        "requires_result",
        "dtype",
        "colormap",
        "value_range",
        "unit",
        "category",
    )

    def __init__(
        self,
        name: str,
        requires_result: bool,
        dtype: MapDtype = "scalar",
        colormap: str | None = None,
        value_range: tuple[float, float] | None = None,
        unit: str | None = None,
        category: str | None = None,
    ):
        self.name = name
        self.requires_result = requires_result
        self.dtype = dtype
        self.colormap = colormap
        self.value_range = value_range
        self.unit = unit
        self.category = category


def _empty_for_dtype(shape: tuple[int, ...], dtype: MapDtype) -> np.ndarray:
    if dtype == "rgb":
        return np.zeros((*shape, 3))
    if dtype == "discrete":
        return np.zeros(shape, dtype=np.float32)
    return np.full(shape, np.nan)


def map_property(
    name: str,
    requires_result: bool = False,
    dtype: MapDtype = "scalar",
    colormap: str | None = None,
    value_range: tuple[float, float] | None = None,
    unit: str | None = None,
    category: str | None = None,
) -> Callable:
    meta = _MapPropertyMeta(
        name,
        requires_result,
        dtype=dtype,
        colormap=colormap,
        value_range=value_range,
        unit=unit,
        category=category,
    )

    def decorator(fn: Callable) -> Callable:
        if requires_result:

            @functools.wraps(fn)
            def wrapper(self, *args, **kwargs):
                if self._result is None:
                    return _empty_for_dtype(self.shape, dtype)
                return fn(self, *args, **kwargs)

            setattr(wrapper, _MAP_PROPERTY_ATTR, meta)
            return wrapper
        setattr(fn, _MAP_PROPERTY_ATTR, meta)
        return fn

    return decorator


class SpatialMap(Displayable):
    @classmethod
    def registered_map_properties(cls) -> list[_MapPropertyMeta]:
        props: list[_MapPropertyMeta] = []
        for klass in cls.__mro__:
            for attr_name, attr in vars(klass).items():
                meta = getattr(attr, _MAP_PROPERTY_ATTR, None)
                if meta is not None:
                    props.append(meta)
        return props

    def compute_map_property(self, name: str, **kwargs: Any) -> np.ndarray:
        for klass in type(self).__mro__:
            for attr_name, attr in vars(klass).items():
                meta = getattr(attr, _MAP_PROPERTY_ATTR, None)
                if meta is not None and meta.name == name:
                    try:
                        return getattr(self, attr_name)(**kwargs)
                    except Exception as e:
                        logging.getLogger(__name__).error(
                            "Error computing %s: %s", name, e
                        )
                        raise
        msg = f"Unknown map property: {name}"
        raise KeyError(msg)
