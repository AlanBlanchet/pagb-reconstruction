from collections.abc import Callable
from typing import ClassVar

import numpy as np
from orix.quaternion import Orientation
from pydantic import ConfigDict

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.core.phase import PhaseConfig


def _register(key: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        fn._preset_key = key
        return fn

    return decorator


class OrientationRelationship(Displayable):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    parallel_planes_parent: tuple[int, int, int]
    parallel_planes_child: tuple[int, int, int]
    parallel_dirs_parent: tuple[int, int, int]
    parallel_dirs_child: tuple[int, int, int]
    parent_phase: PhaseConfig
    child_phase: PhaseConfig
    _rotation_matrix: np.ndarray | None = None
    OR_PRESETS: ClassVar[dict[str, Callable]] = {}

    DEFAULT_PARENT: ClassVar[PhaseConfig | None] = None
    DEFAULT_CHILD: ClassVar[PhaseConfig | None] = None

    @classmethod
    def _default_parent(cls) -> PhaseConfig:
        return cls.DEFAULT_PARENT or PhaseConfig.austenite()

    @classmethod
    def _default_child(cls) -> PhaseConfig:
        return cls.DEFAULT_CHILD or PhaseConfig.martensite()

    @classmethod
    def preset_names(cls) -> list[str]:
        if not cls.OR_PRESETS:
            cls._collect_presets()
        return list(cls.OR_PRESETS)

    @classmethod
    def from_preset(
        cls,
        key: str,
        parent: PhaseConfig | None = None,
        child: PhaseConfig | None = None,
    ):
        if not cls.OR_PRESETS:
            cls._collect_presets()
        return cls.OR_PRESETS[key](parent=parent, child=child)

    @classmethod
    def _collect_presets(cls):
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            if callable(attr) and hasattr(attr, "_preset_key"):
                cls.OR_PRESETS[attr._preset_key] = attr

    @property
    def n_variants(self) -> int:
        return len(self.variant_quaternions())

    @property
    def rotation_matrix(self) -> np.ndarray:
        if self._rotation_matrix is not None:
            return self._rotation_matrix
        return self._compute_rotation_matrix()

    def _compute_rotation_matrix(self) -> np.ndarray:
        pp = np.array(self.parallel_planes_parent, dtype=float)
        pc = np.array(self.parallel_planes_child, dtype=float)
        dp = np.array(self.parallel_dirs_parent, dtype=float)
        dc = np.array(self.parallel_dirs_child, dtype=float)

        pp /= np.linalg.norm(pp)
        pc /= np.linalg.norm(pc)
        dp /= np.linalg.norm(dp)
        dc /= np.linalg.norm(dc)

        pp3 = np.cross(pp, dp)
        pp3 /= np.linalg.norm(pp3)
        pc3 = np.cross(pc, dc)
        pc3 /= np.linalg.norm(pc3)

        parent_basis = np.column_stack([dp, pp, pp3])
        child_basis = np.column_stack([dc, pc, pc3])

        R = child_basis @ np.linalg.inv(parent_basis)
        self._rotation_matrix = R
        return R

    def variant_quaternions(self) -> np.ndarray:
        R = self.rotation_matrix
        parent_sym = self.parent_phase.symmetry

        or_ori = Orientation.from_matrix(R.reshape(1, 3, 3))
        parent_syms = Orientation(parent_sym.data)
        variants = []
        seen: set[tuple[float, ...]] = set()

        for ps in parent_syms:
            variant = ps * or_ori
            q = variant.data.flatten()
            if q[0] < 0:
                q = -q
            key = tuple(np.round(q, 4))
            if key not in seen:
                seen.add(key)
                variants.append(q)

        return np.array(variants)

    def candidate_parents(self, child_quaternion: np.ndarray) -> np.ndarray:
        variants = self.variant_quaternions()
        child_ori = Orientation(child_quaternion.reshape(1, 4))
        candidates = []

        for v in variants:
            var_ori = Orientation(v.reshape(1, 4))
            parent = child_ori * (~var_ori)
            q = parent.data.flatten()
            if q[0] < 0:
                q = -q
            candidates.append(q)

        return np.array(candidates)

    def theoretical_misorientations(self) -> np.ndarray:
        variants = self.variant_quaternions()
        n = len(variants)
        misoris = []

        for i in range(n):
            for j in range(i + 1, n):
                v1 = Orientation(
                    variants[i].reshape(1, 4), symmetry=self.child_phase.symmetry
                )
                v2 = Orientation(
                    variants[j].reshape(1, 4), symmetry=self.child_phase.symmetry
                )
                mori = (~v1) * v2
                angle = float(mori.angle.data[0]) * 180.0 / np.pi
                misoris.append(angle)

        return np.array(misoris)

    @classmethod
    @_register("KS")
    def kurdjumov_sachs(
        cls, parent: PhaseConfig | None = None, child: PhaseConfig | None = None
    ):
        return cls(
            name="Kurdjumov-Sachs",
            description="(111)fcc // (011)bcc, [-101]fcc // [-1-11]bcc",
            parallel_planes_parent=(1, 1, 1),
            parallel_planes_child=(0, 1, 1),
            parallel_dirs_parent=(1, 0, -1),
            parallel_dirs_child=(1, -1, 1),
            parent_phase=parent or cls._default_parent(),
            child_phase=child or cls._default_child(),
        )

    @classmethod
    @_register("NW")
    def nishiyama_wassermann(
        cls, parent: PhaseConfig | None = None, child: PhaseConfig | None = None
    ):
        return cls(
            name="Nishiyama-Wassermann",
            description="(111)fcc // (011)bcc, [11-2]fcc // [0-11]bcc",
            parallel_planes_parent=(1, 1, 1),
            parallel_planes_child=(0, 1, 1),
            parallel_dirs_parent=(1, 1, -2),
            parallel_dirs_child=(0, -1, 1),
            parent_phase=parent or cls._default_parent(),
            child_phase=child or cls._default_child(),
        )

    @classmethod
    @_register("GT")
    def greninger_troiano(
        cls, parent: PhaseConfig | None = None, child: PhaseConfig | None = None
    ):
        return cls(
            name="Greninger-Troiano",
            description="(111)fcc // (011)bcc, [5 12 -17]fcc // [17 -7 17]bcc",
            parallel_planes_parent=(1, 1, 1),
            parallel_planes_child=(0, 1, 1),
            parallel_dirs_parent=(5, 12, -17),
            parallel_dirs_child=(17, -7, 17),
            parent_phase=parent or cls._default_parent(),
            child_phase=child or cls._default_child(),
        )

    @classmethod
    @_register("Pitsch")
    def pitsch(
        cls, parent: PhaseConfig | None = None, child: PhaseConfig | None = None
    ):
        return cls(
            name="Pitsch",
            description="(010)fcc // (101)bcc, [101]fcc // [1-11]bcc",
            parallel_planes_parent=(0, 1, 0),
            parallel_planes_child=(1, 0, 1),
            parallel_dirs_parent=(1, 0, 1),
            parallel_dirs_child=(1, -1, 1),
            parent_phase=parent or cls._default_parent(),
            child_phase=child or cls._default_child(),
        )

    @classmethod
    @_register("Bain")
    def bain(cls, parent: PhaseConfig | None = None, child: PhaseConfig | None = None):
        return cls(
            name="Bain",
            description="(001)fcc // (001)bcc, [100]fcc // [110]bcc",
            parallel_planes_parent=(0, 0, 1),
            parallel_planes_child=(0, 0, 1),
            parallel_dirs_parent=(1, 0, 0),
            parallel_dirs_child=(1, 1, 0),
            parent_phase=parent or cls._default_parent(),
            child_phase=child or cls._default_child(),
        )


OrientationRelationship._collect_presets()
