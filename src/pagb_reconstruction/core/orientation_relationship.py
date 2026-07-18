from collections.abc import Callable
from typing import ClassVar

import numpy as np
from orix.quaternion import Orientation

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.core.phase import PhaseConfig
from pagb_reconstruction.utils.compute import Quaternions
from pagb_reconstruction.utils.math_ops import MisorientationOps


def _register(key: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        fn._preset_key = key
        return fn

    return decorator


class OrientationRelationship(Displayable):

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
    # Display order, most relevant first. KS leads: it is the standard OR for
    # prior-austenite reconstruction in steels and the ReconstructionConfig
    # default. Without this, presets order alphabetically by method name and
    # the UI would default to Bain — wrong for steel.
    PRESET_ORDER: ClassVar[tuple[str, ...]] = ("KS", "NW", "GT", "Pitsch", "Bain")

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
        ordered = [k for k in cls.PRESET_ORDER if k in cls.OR_PRESETS]
        extras = [k for k in cls.OR_PRESETS if k not in cls.PRESET_ORDER]
        return ordered + extras

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
            variant = or_ori * ps
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
            parent = (~var_ori) * child_ori
            q = parent.data.flatten()
            if q[0] < 0:
                q = -q
            candidates.append(q)

        return np.array(candidates)

    def candidate_parents_batch(self, child_quaternions: np.ndarray) -> np.ndarray:
        """Vectorised :meth:`candidate_parents` over many children at once:
        ``(n, 4)`` child quaternions → ``(n, K, 4)`` candidate parents, on the
        compute device (GPU when available). Replaces the per-grain orix loop
        that dominated ``build_variant_graph``."""
        return Quaternions.candidate_parents(
            self.variant_quaternions(), np.asarray(child_quaternions)
        )

    def variant_merge_groups(self, merge_deg: float) -> list[list[int]]:
        """Pair up variants with a small mutual misorientation (Hielscher et
        al. 2022 §5.4: KS block pairs V1–V4 at 10.53° merge 24→12, cutting
        variant-graph edges and memory 4×). ``merge_deg`` sits between the
        lowest inter-variant angle and the next spectrum line (12° pairs the
        10.53° KS blocks; next line is 14.88°). This is a MATCHING, not a
        transitive union — each KS Bain group is an 8-cycle of 10.53° edges,
        so union-find would collapse whole Bain groups instead of pairs.
        ``merge_deg <= 0`` disables merging (one group per variant)."""
        variants = np.ascontiguousarray(self.variant_quaternions(), dtype=np.float64)
        n = len(variants)
        if merge_deg <= 0:
            return [[i] for i in range(n)]

        csym = np.ascontiguousarray(self.child_phase.symmetry.data, dtype=np.float64)
        angle = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                angle[i, j] = angle[j, i] = MisorientationOps._angle_with_symmetry(
                    variants[i], variants[j], csym
                )
        adj = {
            i: sorted(j for j in range(n) if j != i and angle[i, j] < merge_deg)
            for i in range(n)
        }

        matched = [False] * n
        groups: list[list[int]] = []
        seen: set[int] = set()
        for start in range(n):
            if start in seen:
                continue
            # component walk
            comp, stack = [], [start]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                comp.append(x)
                stack += adj[x]
            comp.sort()
            degrees = {i: len(adj[i]) for i in comp}
            if len(comp) % 2 == 0 and all(d == 2 for d in degrees.values()):
                # even cycle (the KS Bain-group shape) → alternate-edge pairing
                order, cur, prev = [comp[0]], comp[0], -1
                while len(order) < len(comp):
                    nxt = next(j for j in adj[cur] if j != prev)
                    order.append(nxt)
                    prev, cur = cur, nxt
                for k in range(0, len(order), 2):
                    groups.append(sorted((order[k], order[k + 1])))
                    matched[order[k]] = matched[order[k + 1]] = True
            else:
                # generic fallback: greedy min-angle matching, leftovers single
                pairs = sorted(
                    ((angle[i, j], i, j) for i in comp for j in adj[i] if i < j)
                )
                for _, i, j in pairs:
                    if not matched[i] and not matched[j]:
                        groups.append([i, j])
                        matched[i] = matched[j] = True
                for i in comp:
                    if not matched[i]:
                        groups.append([i])
                        matched[i] = True
        return sorted(groups)

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
