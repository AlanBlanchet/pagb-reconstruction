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
from pagb_reconstruction.utils.math_ops import (
    misorientation_angle_neighbors,
    misorientation_angle_pair,
    misorientation_axis_angle_pair,
)


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

    @map_property("Phase", dtype="discrete", category="phase")
    def phase_map(self) -> np.ndarray:
        return self.crystal_map.phase_id.reshape(self.shape)

    @map_property("IPF-Z", dtype="rgb", category="orientation")
    def ipf_z_map(self) -> np.ndarray:
        return self._ipf_map(Vector3d.zvector())

    @map_property("IPF-X", dtype="rgb", category="orientation")
    def ipf_x_map(self) -> np.ndarray:
        return self._ipf_map(Vector3d.xvector())

    @map_property("IPF-Y", dtype="rgb", category="orientation")
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

    @map_property("Euler Angles", dtype="rgb", category="orientation")
    def euler_angle_map(self) -> np.ndarray:
        euler = self.crystal_map.rotations.to_euler(degrees=True)
        return euler.reshape(*self.shape, 3)

    @map_property("Grain ID", dtype="discrete", category="microstructure")
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

    @map_property("Band Contrast", dtype="scalar", category="quality")
    def band_contrast_map(self) -> np.ndarray:
        for key in ("bc", "iq", "ci"):
            prop = self.crystal_map.prop.get(key)
            if prop is not None:
                return prop.reshape(self.shape)
        return np.zeros(self.shape)

    def _primary_symmetry_quats(self) -> np.ndarray:
        phases = self.crystal_map.phases_in_data
        return phases[phases.ids[0]].point_group.data

    @map_property("KAM", dtype="scalar", unit="\u00b0", colormap="inferno", category="deformation")
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

    @map_property("Parent Grain ID", requires_result=True, dtype="discrete", category="reconstruction")
    def parent_grain_id_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros(self.shape, dtype=np.float32)
        return self._result.parent_grain_ids.reshape(self.shape).astype(np.float32)

    @map_property("Variant ID", requires_result=True, dtype="discrete", category="reconstruction")
    def variant_id_map(self) -> np.ndarray:
        if self._result is None:
            return np.zeros(self.shape, dtype=np.float32)
        return self._result.variant_ids.reshape(self.shape).astype(np.float32)

    @map_property("Fit Quality", requires_result=True, dtype="scalar", unit="\u00b0", colormap="RdYlGn_r", category="reconstruction")
    def fit_quality_map(self) -> np.ndarray:
        if self._result is None:
            return np.full(self.shape, np.nan)
        return self._result.fit_angles.reshape(self.shape)

    @map_property("Parent IPF", requires_result=True, dtype="rgb", category="reconstruction")
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

    @map_property("Parent + Boundaries", requires_result=True, dtype="rgb", category="reconstruction")
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

    @map_property("GOS", dtype="scalar", unit="\u00b0", colormap="hot", category="deformation")
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

    @map_property("Misorientation", dtype="scalar", unit="\u00b0", colormap="viridis", category="deformation")
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

    @map_property("GROD", dtype="scalar", unit="\u00b0", colormap="hot", category="deformation")
    def grod_map(self) -> np.ndarray:
        grod = np.zeros(self.shape, dtype=np.float64)
        if not self.grains:
            return grod
        rows, cols = self.shape
        sym_quats = self._primary_symmetry_quats()
        for g in self.grains:
            for px in g.pixel_indices:
                angle = misorientation_angle_pair(
                    self.quaternions[px], g.mean_quaternion, sym_quats
                )
                r, c = px // cols, px % cols
                grod[r, c] = angle
        return grod

    @map_property("Schmid Factor", dtype="scalar", value_range=(0.0, 0.5), colormap="coolwarm", category="mechanical")
    def schmid_factor_map(self) -> np.ndarray:
        rows, cols = self.shape
        n_pixels = rows * cols
        schmid = np.zeros(n_pixels, dtype=np.float64)
        phases = self.crystal_map.phases_in_data

        bcc_planes = np.array([[1,1,0],[1,0,1],[0,1,1],[1,-1,0],[1,0,-1],[0,1,-1]], dtype=np.float64)
        bcc_dirs = np.array([[1,-1,1],[1,1,-1],[-1,1,1],[1,1,1],[1,-1,1],[1,1,-1]], dtype=np.float64)
        fcc_planes = np.array([[1,1,1],[1,1,1],[1,1,1],[1,-1,1],[1,-1,1],[1,-1,1]], dtype=np.float64)
        fcc_dirs = np.array([[1,-1,0],[0,1,-1],[-1,0,1],[1,1,0],[0,1,1],[-1,0,1]], dtype=np.float64)

        for pid in phases.ids:
            mask = self.crystal_map.phase_id == pid
            pg = str(phases[pid].point_group)
            if "m-3m" in pg or "432" in pg:
                family = phases[pid].point_group
                sym_size = family.size
                if sym_size <= 24:
                    planes, dirs = bcc_planes, bcc_dirs
                else:
                    planes, dirs = fcc_planes, fcc_dirs
            else:
                continue

            indices = np.where(mask)[0]
            rotations = self.crystal_map[mask].rotations
            oris = Orientation(rotations, symmetry=phases[pid].point_group)
            loading = Vector3d([0, 0, 1])

            for k, idx in enumerate(indices):
                ori = oris[k]
                max_sf = 0.0
                for sl in range(len(planes)):
                    n_crystal = Vector3d(planes[sl])
                    d_crystal = Vector3d(dirs[sl])
                    n_sample = ori * n_crystal
                    d_sample = ori * d_crystal
                    n_norm = n_sample.unit
                    d_norm = d_sample.unit
                    cos_phi = abs(float(n_norm.dot(loading).data[0]))
                    cos_lam = abs(float(d_norm.dot(loading).data[0]))
                    sf = cos_phi * cos_lam
                    if sf > max_sf:
                        max_sf = sf
                schmid[idx] = max_sf

        return schmid.reshape(self.shape)

    @map_property("CSL Boundaries", dtype="rgb", category="microstructure")
    def csl_boundary_map(self) -> np.ndarray:
        rows, cols = self.shape
        sym_quats = self._primary_symmetry_quats()
        rgb = np.ones((rows, cols, 3), dtype=np.float64)

        sigma3_angle, sigma3_tol = 60.0, 8.66
        sigma3_axis = np.array([1, 1, 1], dtype=np.float64)
        sigma3_axis /= np.linalg.norm(sigma3_axis)

        sigma9_angle, sigma9_tol = 38.94, 5.0
        sigma9_axis = np.array([1, 1, 0], dtype=np.float64)
        sigma9_axis /= np.linalg.norm(sigma9_axis)

        quats = self.quaternions

        for r in range(rows):
            for c in range(cols - 1):
                idx1 = r * cols + c
                idx2 = r * cols + c + 1
                angle, axis = misorientation_axis_angle_pair(quats[idx1], quats[idx2], sym_quats)
                color = self._classify_csl(angle, axis, sigma3_angle, sigma3_axis, sigma3_tol,
                                           sigma9_angle, sigma9_axis, sigma9_tol)
                if color is not None:
                    rgb[r, c] = color
                    rgb[r, c + 1] = color

        for r in range(rows - 1):
            for c in range(cols):
                idx1 = r * cols + c
                idx2 = (r + 1) * cols + c
                angle, axis = misorientation_axis_angle_pair(quats[idx1], quats[idx2], sym_quats)
                color = self._classify_csl(angle, axis, sigma3_angle, sigma3_axis, sigma3_tol,
                                           sigma9_angle, sigma9_axis, sigma9_tol)
                if color is not None:
                    rgb[r, c] = color
                    rgb[r + 1, c] = color

        return rgb

    def _classify_csl(
        self,
        angle: float,
        axis: np.ndarray,
        s3_angle: float,
        s3_axis: np.ndarray,
        s3_tol: float,
        s9_angle: float,
        s9_axis: np.ndarray,
        s9_tol: float,
    ) -> np.ndarray | None:
        if angle < 2.0:
            return np.array([0.7, 0.7, 0.7])
        if angle < 15.0:
            return np.array([0.5, 0.5, 0.5])
        axis_norm = np.linalg.norm(axis)
        if axis_norm < 1e-10:
            return np.array([0.0, 0.0, 0.0])
        axis_unit = axis / axis_norm
        if abs(angle - s3_angle) < s3_tol and abs(np.dot(axis_unit, s3_axis)) > 0.9:
            return np.array([1.0, 0.0, 0.0])
        if abs(angle - s9_angle) < s9_tol and abs(np.dot(axis_unit, s9_axis)) > 0.9:
            return np.array([0.0, 0.0, 1.0])
        if angle >= 15.0:
            return np.array([0.0, 0.0, 0.0])
        return None
