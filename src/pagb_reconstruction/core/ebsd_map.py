from typing import Any

import matplotlib
import numpy as np
from orix.crystal_map import CrystalMap
from orix.plot import IPFColorKeyTSL
from orix.quaternion import Orientation
from orix.vector import Vector3d
from pydantic import ConfigDict

from pagb_reconstruction.core.base import SpatialMap, map_property
from pagb_reconstruction.core.grain import Grain, detect_grains
from pagb_reconstruction.core.phase import PhaseConfig
from pagb_reconstruction.utils.math_ops import misorientation_angle_neighbors, misorientation_angle_pair


class EBSDMap(SpatialMap):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    crystal_map: CrystalMap
    phases: list[PhaseConfig]
    grains: list[Grain] | None = None
    parent_map: CrystalMap | None = None
    _result: Any = None

    def set_result(self, result: Any):
        self._result = result

    @property
    def orientations(self) -> Orientation:
        return self.crystal_map.orientations

    @property
    def quaternions(self) -> np.ndarray:
        return self.crystal_map.rotations.data

    @property
    def coordinates(self) -> np.ndarray:
        return np.column_stack([self.crystal_map.x, self.crystal_map.y])

    @property
    def shape(self) -> tuple[int, int]:
        return (
            (self.crystal_map.shape[0], self.crystal_map.shape[1])
            if len(self.crystal_map.shape) == 2
            else (self.crystal_map.shape[0], 1)
        )

    @property
    def step_size(self) -> tuple[float, float]:
        dx = self.crystal_map.dx
        dy = self.crystal_map.dy
        return (float(dy) if dy else 1.0, float(dx) if dx else 1.0)

    @property
    def phase_ids(self) -> np.ndarray:
        return self.crystal_map.phase_id

    def property_map(self, name: str) -> np.ndarray:
        prop = self.crystal_map.prop.get(name)
        if prop is None:
            return np.zeros(self.shape)
        return prop.reshape(self.shape)

    @map_property("Phase")
    def phase_map(self) -> np.ndarray:
        return self.crystal_map.phase_id.reshape(self.shape)

    @map_property("IPF-Z")
    def ipf_z_map(self) -> np.ndarray:
        return self._ipf_map(Vector3d.zvector())

    @map_property("IPF-X")
    def ipf_x_map(self) -> np.ndarray:
        return self._ipf_map(Vector3d.xvector())

    @map_property("IPF-Y")
    def ipf_y_map(self) -> np.ndarray:
        return self._ipf_map(Vector3d.yvector())

    def ipf_map(self, direction: Vector3d | None = None) -> np.ndarray:
        from pagb_reconstruction.utils.colormap import DEFAULT_IPF_DIRECTION

        return self._ipf_map(direction or DEFAULT_IPF_DIRECTION)

    def _ipf_map(self, direction: Vector3d) -> np.ndarray:
        from pagb_reconstruction.utils.colormap import ipf_colors

        n_pixels = self.crystal_map.size
        rgb = np.zeros((n_pixels, 3))
        phases = self.crystal_map.phases_in_data
        for pid in phases.ids:
            mask = self.crystal_map.phase_id == pid
            rotations = self.crystal_map[mask].rotations
            ori = Orientation(rotations, symmetry=phases[pid].point_group)
            rgb[mask] = ipf_colors(ori, direction)
        return rgb.reshape(*self.shape, 3)

    @map_property("Euler Angles")
    def euler_angle_map(self) -> np.ndarray:
        euler = self.crystal_map.rotations.to_euler(degrees=True)
        return euler.reshape(*self.shape, 3)

    @map_property("Grain ID")
    def grain_id_map(self) -> np.ndarray:
        gmap = np.zeros(self.shape, dtype=np.float32)
        if not self.grains:
            return gmap
        cols = self.shape[1]
        for g in self.grains:
            r = g.pixel_indices // cols
            c = g.pixel_indices % cols
            gmap[r, c] = g.id
        return gmap

    @map_property("Band Contrast")
    def band_contrast_map(self) -> np.ndarray:
        for key in ("bc", "iq", "ci"):
            prop = self.crystal_map.prop.get(key)
            if prop is not None:
                return prop.reshape(self.shape)
        return np.zeros(self.shape)

    def _primary_symmetry_quats(self) -> np.ndarray:
        phases = self.crystal_map.phases_in_data
        return phases[phases.ids[0]].point_group.data

    @map_property("KAM")
    def kam_map(self) -> np.ndarray:
        sym_quats = self._primary_symmetry_quats()
        misori_h, misori_v = misorientation_angle_neighbors(
            self.quaternions, self.shape, sym_quats
        )
        rows, cols = self.shape
        kam = np.zeros((rows, cols), dtype=np.float64)
        count = np.zeros((rows, cols), dtype=np.float64)

        if misori_h.size == rows * (cols - 1):
            h = misori_h.reshape(rows, cols - 1)
            kam[:, 1:] += h
            kam[:, :-1] += h
            count[:, 1:] += 1
            count[:, :-1] += 1

        if misori_v.size == (rows - 1) * cols:
            v = misori_v.reshape(rows - 1, cols)
            kam[1:, :] += v
            kam[:-1, :] += v
            count[1:, :] += 1
            count[:-1, :] += 1

        count[count == 0] = 1.0
        return kam / count

    @map_property("Parent Grain ID", requires_result=True)
    def parent_grain_id_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros(self.shape, dtype=np.float32)
        return self._result.parent_grain_ids.reshape(self.shape).astype(np.float32)

    @map_property("Variant ID", requires_result=True)
    def variant_id_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros(self.shape, dtype=np.float32)
        return self._result.variant_ids.reshape(self.shape).astype(np.float32)

    @map_property("Fit Quality", requires_result=True)
    def fit_quality_map(self) -> np.ndarray:
        if self._result is None:
            return np.full(self.shape, np.nan)
        return self._result.fit_angles.reshape(self.shape)

    @map_property("Parent IPF", requires_result=True)
    def parent_ipf_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros((*self.shape, 3))
        parent_quats = self._result.parent_orientations
        phases = self.crystal_map.phases_in_data
        sym = phases[phases.ids[0]].point_group
        ori = Orientation(parent_quats.reshape(-1, 4), symmetry=sym)
        key = IPFColorKeyTSL(sym, direction=Vector3d.zvector())
        rgb = key.orientation2color(ori).reshape(*self.shape, 3)
        parent_ids = self._result.parent_grain_ids.reshape(self.shape)
        boundary = self._boundary_from_ids(parent_ids)
        rgb[boundary] = 0.1
        return rgb

    @map_property("Parent + Boundaries", requires_result=True)
    def parent_boundary_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros((*self.shape, 3))
        parent_ids = self._result.parent_grain_ids.reshape(self.shape)
        unique_ids = np.unique(parent_ids)
        cmap = matplotlib.colormaps["tab20"]
        rgb = np.zeros((*self.shape, 3))
        for i, gid in enumerate(unique_ids):
            color = cmap(i % 20)[:3]
            rgb[parent_ids == gid] = color
        boundary = self._boundary_from_ids(parent_ids)
        rgb[boundary] = 0.0
        return rgb

    @map_property("GOS")
    def gos_map(self) -> np.ndarray:
        gos = np.zeros(self.shape, dtype=np.float64)
        if not self.grains:
            return gos
        rows, cols = self.shape
        sym_quats = self._primary_symmetry_quats()
        for g in self.grains:
            angles = np.array([
                misorientation_angle_pair(self.quaternions[px], g.mean_quaternion, sym_quats)
                for px in g.pixel_indices
            ])
            val = angles.mean()
            r = g.pixel_indices // cols
            c = g.pixel_indices % cols
            gos[r, c] = val
        return gos

    @map_property("Misorientation")
    def misorientation_map(self) -> np.ndarray:
        sym_quats = self._primary_symmetry_quats()
        misori_h, misori_v = misorientation_angle_neighbors(
            self.quaternions, self.shape, sym_quats
        )
        rows, cols = self.shape
        h_full = np.zeros((rows, cols), dtype=np.float64)
        v_full = np.zeros((rows, cols), dtype=np.float64)
        h_full[:, :-1] = misori_h.reshape(rows, cols - 1)
        v_full[:-1, :] = misori_v.reshape(rows - 1, cols)
        return np.maximum(h_full, v_full)

    def run_grain_detection(self, threshold_deg: float = 5.0, min_size: int = 5):
        sym_quats = self._primary_symmetry_quats()
        self.grains = detect_grains(
            quaternions=self.quaternions,
            phase_ids=self.phase_ids,
            shape=self.shape,
            symmetry_quats=sym_quats,
            threshold_deg=threshold_deg,
            min_size=min_size,
        )

    def _boundary_from_ids(self, id_map: np.ndarray) -> np.ndarray:
        rows, cols = id_map.shape
        boundary = np.zeros((rows, cols), dtype=bool)
        boundary[:, :-1] |= id_map[:, :-1] != id_map[:, 1:]
        boundary[:-1, :] |= id_map[:-1, :] != id_map[1:, :]
        return boundary

    def grain_boundary_map(self) -> np.ndarray:
        sym_quats = self._primary_symmetry_quats()
        misori_h, misori_v = misorientation_angle_neighbors(
            self.quaternions, self.shape, sym_quats
        )

        rows, cols = self.shape
        boundary = np.zeros((rows, cols), dtype=bool)
        if misori_h.size == rows * (cols - 1):
            boundary[:, 1:] |= misori_h.reshape(rows, cols - 1) >= 5.0
        if misori_v.size == (rows - 1) * cols:
            boundary[1:, :] |= misori_v.reshape(rows - 1, cols) >= 5.0
        return boundary
