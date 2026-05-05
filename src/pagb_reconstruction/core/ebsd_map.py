from typing import Any

import matplotlib
import numpy as np
from orix.crystal_map import CrystalMap
from orix.plot import IPFColorKeyTSL
from orix.quaternion import Orientation
from orix.vector import Vector3d
from pydantic import BaseModel, ConfigDict
from scipy.spatial import cKDTree

from pagb_reconstruction.core.base import SpatialMap, map_property
from pagb_reconstruction.core.constants import (
    BoundaryThresholds,
    CSLParams,
    SlipSystems,
)
from pagb_reconstruction.core.grain import Grain, detect_grains
from pagb_reconstruction.core.phase import PhaseConfig
from pagb_reconstruction.utils.array_ops import boundaries_from_2d
from pagb_reconstruction.utils.colormap import DEFAULT_IPF_DIRECTION, ipf_colors
from pagb_reconstruction.utils.math_ops import MisorientationOps


class PixelTopology(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    pairs: np.ndarray
    n_pixels: int
    grid_shape: tuple[int, int]
    pixel_to_rc: np.ndarray
    degree: np.ndarray

    @classmethod
    def from_crystal_map(cls, xmap: CrystalMap):
        x, y = xmap.x, xmap.y
        dx, dy = float(xmap.dx or 1), float(xmap.dy or 1)
        coords = np.column_stack([x, y])
        tree = cKDTree(coords)

        sample_size = min(100, len(x))
        dists, _ = tree.query(coords[:sample_size], k=2)
        nn_dist = float(np.median(dists[:, 1]))
        r = nn_dist * 1.01

        pair_set = tree.query_pairs(r, output_type="ndarray").astype(np.int32)

        rows = np.round((y - y.min()) / dy).astype(int)
        cols = np.round((x - x.min()) / dx).astype(int)
        grid_shape = (int(rows.max() + 1), int(cols.max() + 1))
        pixel_to_rc = np.column_stack([rows, cols])

        degree = np.zeros(len(x), dtype=np.int32)
        np.add.at(degree, pair_set[:, 0], 1)
        np.add.at(degree, pair_set[:, 1], 1)

        return cls(
            pairs=pair_set,
            n_pixels=len(x),
            grid_shape=grid_shape,
            pixel_to_rc=pixel_to_rc,
            degree=degree,
        )


class EBSDMap(SpatialMap):
    crystal_map: CrystalMap
    phases: list[PhaseConfig]
    grains: list[Grain] | None = None
    parent_map: CrystalMap | None = None
    _result: Any = None
    _topology: PixelTopology | None = None

    def set_result(self, result: Any):
        self._result = result

    @property
    def topology(self) -> PixelTopology:
        if self._topology is None:
            self._topology = PixelTopology.from_crystal_map(self.crystal_map)
        return self._topology

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

    @property
    def is_sparse(self) -> bool:
        rows, cols = self.shape
        return self.crystal_map.size != rows * cols

    def _to_grid(self, data: np.ndarray, fill: float = 0.0) -> np.ndarray:
        if not self.is_sparse:
            if data.ndim == 1:
                return data.reshape(self.shape)
            return data.reshape(*self.shape, *data.shape[1:])
        rc = self.topology.pixel_to_rc
        rows, cols = rc[:, 0], rc[:, 1]
        if data.ndim == 1:
            grid = np.full(self.shape, fill, dtype=data.dtype)
            grid[rows, cols] = data
        else:
            grid = np.full((*self.shape, *data.shape[1:]), fill, dtype=data.dtype)
            grid[rows, cols] = data
        return grid

    def pixel_index_at(self, grid_row: int, grid_col: int) -> int:
        rc = self.topology.pixel_to_rc
        matches = np.where((rc[:, 0] == grid_row) & (rc[:, 1] == grid_col))[0]
        if len(matches) == 0:
            return -1
        return int(matches[0])

    def property_map(self, name: str) -> np.ndarray:
        prop = self.crystal_map.prop.get(name)
        if prop is None:
            return np.zeros(self.shape)
        return self._to_grid(prop)

    @map_property("Phase", dtype="discrete", category="phase")
    def phase_map(self) -> np.ndarray:
        return self._to_grid(self.crystal_map.phase_id)

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
        return self._ipf_map(direction or DEFAULT_IPF_DIRECTION)

    def _ipf_map(self, direction: Vector3d) -> np.ndarray:

        n_pixels = self.crystal_map.size
        rgb = np.zeros((n_pixels, 3))
        phases = self.crystal_map.phases_in_data
        for pid in phases.ids:
            if pid < 0 or phases[pid].point_group is None:
                continue
            mask = self.crystal_map.phase_id == pid
            rotations = self.crystal_map[mask].rotations
            ori = Orientation(rotations, symmetry=phases[pid].point_group)
            rgb[mask] = ipf_colors(ori, direction)
        return self._to_grid(rgb)

    @map_property("Euler Angles", dtype="rgb", category="orientation")
    def euler_angle_map(self) -> np.ndarray:
        euler = self.crystal_map.rotations.to_euler(degrees=True)
        return self._to_grid(euler)

    @map_property("Grain ID", dtype="discrete", category="microstructure")
    def grain_id_map(self) -> np.ndarray:
        gmap = np.zeros(self.topology.n_pixels, dtype=np.float32)
        if not self.grains:
            return self._to_grid(gmap)
        for g in self.grains:
            gmap[g.pixel_indices] = g.id
        return self._to_grid(gmap)

    @map_property("Band Contrast", dtype="scalar", category="quality")
    def band_contrast_map(self) -> np.ndarray:
        props = self.crystal_map.prop
        keys_lower = {k.lower(): k for k in props}
        for candidate in ("bc", "iq", "ci"):
            real_key = keys_lower.get(candidate)
            if real_key is not None:
                return self._to_grid(props[real_key])
        return np.zeros(self.shape)

    def _primary_symmetry_quats(self) -> np.ndarray:
        phases = self.crystal_map.phases_in_data
        for pid in phases.ids:
            if pid >= 0 and phases[pid].point_group is not None:
                return phases[pid].point_group.data
        raise ValueError("No indexed phase with point group found")

    def _pair_angles(self):
        topo = self.topology
        angles = MisorientationOps.pairs(
            self.quaternions, topo.pairs, self._primary_symmetry_quats()
        )
        return topo, angles

    @map_property(
        "KAM", dtype="scalar", unit="\u00b0", colormap="inferno", category="deformation"
    )
    def kam_map(self) -> np.ndarray:
        topo, angles = self._pair_angles()
        kam = np.zeros(topo.n_pixels, dtype=np.float64)
        np.add.at(kam, topo.pairs[:, 0], angles)
        np.add.at(kam, topo.pairs[:, 1], angles)
        return self._to_grid(kam / np.maximum(topo.degree, 1))

    @map_property(
        "Parent Grain ID",
        requires_result=True,
        dtype="discrete",
        category="reconstruction",
    )
    def parent_grain_id_map(self) -> np.ndarray:
        return self._to_grid(self._result.parent_grain_ids).astype(np.float32)

    @map_property(
        "Variant ID", requires_result=True, dtype="discrete", category="reconstruction"
    )
    def variant_id_map(self) -> np.ndarray:
        return self._to_grid(self._result.variant_ids).astype(np.float32)

    @map_property(
        "Fit Quality",
        requires_result=True,
        dtype="scalar",
        unit="\u00b0",
        colormap="RdYlGn_r",
        category="reconstruction",
    )
    def fit_quality_map(self) -> np.ndarray:
        return self._to_grid(self._result.fit_angles, fill=np.nan)

    @map_property(
        "Parent IPF", requires_result=True, dtype="rgb", category="reconstruction"
    )
    def parent_ipf_map(self) -> np.ndarray:
        parent_quats = self._result.parent_orientations
        phases = self.crystal_map.phases_in_data
        sym = None
        for pid in phases.ids:
            if pid >= 0 and phases[pid].point_group is not None:
                sym = phases[pid].point_group
                break
        if sym is None:
            return np.zeros((*self.shape, 3))
        ori = Orientation(parent_quats.reshape(-1, 4), symmetry=sym)
        key = IPFColorKeyTSL(sym, direction=Vector3d.zvector())
        rgb = key.orientation2color(ori)
        rgb_grid = self._to_grid(rgb)
        parent_ids = self._to_grid(self._result.parent_grain_ids)
        boundary = boundaries_from_2d(parent_ids)
        rgb_grid[boundary] = 0.1
        return rgb_grid

    @map_property(
        "Parent + Boundaries",
        requires_result=True,
        dtype="rgb",
        category="reconstruction",
    )
    def parent_boundary_map(self) -> np.ndarray:
        parent_ids = self._to_grid(self._result.parent_grain_ids, fill=-1)
        unique_ids = np.unique(parent_ids)
        cmap = matplotlib.colormaps["tab20"]
        rgb = np.zeros((*self.shape, 3))
        for i, gid in enumerate(unique_ids):
            color = cmap(i % 20)[:3]
            rgb[parent_ids == gid] = color
        boundary = boundaries_from_2d(parent_ids)
        rgb[boundary] = 0.0
        return rgb

    @map_property(
        "GOS", dtype="scalar", unit="\u00b0", colormap="hot", category="deformation"
    )
    def gos_map(self) -> np.ndarray:
        gos = np.zeros(self.topology.n_pixels, dtype=np.float64)
        if not self.grains:
            return self._to_grid(gos)
        sym_quats = self._primary_symmetry_quats()
        for g in self.grains:
            angles = np.array(
                [
                    MisorientationOps.pair(
                        self.quaternions[px], g.mean_quaternion, sym_quats
                    )
                    for px in g.pixel_indices
                ]
            )
            gos[g.pixel_indices] = angles.mean()
        return self._to_grid(gos)

    @map_property(
        "Misorientation",
        dtype="scalar",
        unit="\u00b0",
        colormap="viridis",
        category="deformation",
    )
    def misorientation_map(self) -> np.ndarray:
        topo, angles = self._pair_angles()
        mmap = np.zeros(topo.n_pixels, dtype=np.float64)
        np.maximum.at(mmap, topo.pairs[:, 0], angles)
        np.maximum.at(mmap, topo.pairs[:, 1], angles)
        return self._to_grid(mmap)

    def run_grain_detection(self, threshold_deg: float = 5.0, min_size: int = 5):
        sym_quats = self._primary_symmetry_quats()
        self.grains = detect_grains(
            quaternions=self.quaternions,
            phase_ids=self.phase_ids,
            topology=self.topology,
            symmetry_quats=sym_quats,
            threshold_deg=threshold_deg,
            min_size=min_size,
        )

    def _boundary_from_ids(self, id_map: np.ndarray) -> np.ndarray:
        return boundaries_from_2d(id_map)

    def grain_boundary_map(self) -> np.ndarray:
        _thresholds = BoundaryThresholds()
        topo, angles = self._pair_angles()
        boundary = np.zeros(topo.n_pixels, dtype=bool)
        high = angles >= _thresholds.grain_angle_deg
        boundary_pairs = topo.pairs[high]
        np.bitwise_or.at(boundary, boundary_pairs[:, 0], True)
        np.bitwise_or.at(boundary, boundary_pairs[:, 1], True)
        return self._to_grid(boundary.astype(np.float64))

    @map_property(
        "GROD", dtype="scalar", unit="\u00b0", colormap="hot", category="deformation"
    )
    def grod_map(self) -> np.ndarray:
        if not self.grains:
            return np.zeros(self.shape, dtype=np.float64)
        sym_quats = self._primary_symmetry_quats()
        grod = np.zeros(self.topology.n_pixels, dtype=np.float64)
        for g in self.grains:
            for px in g.pixel_indices:
                grod[px] = MisorientationOps.pair(
                    self.quaternions[px], g.mean_quaternion, sym_quats
                )
        return self._to_grid(grod)

    @map_property(
        "Schmid Factor",
        dtype="scalar",
        value_range=(0.0, 0.5),
        colormap="coolwarm",
        category="mechanical",
    )
    def schmid_factor_map(self) -> np.ndarray:
        n_pixels = self.crystal_map.size
        schmid = np.zeros(n_pixels, dtype=np.float64)
        phases = self.crystal_map.phases_in_data
        _slip = SlipSystems()

        for pid in phases.ids:
            if pid < 0 or phases[pid].point_group is None:
                continue
            mask = self.crystal_map.phase_id == pid
            pg = str(phases[pid].point_group)
            if "m-3m" in pg or "432" in pg:
                family = phases[pid].point_group
                sym_size = family.size
                if sym_size <= 24:
                    planes, dirs = _slip.bcc_planes, _slip.bcc_dirs
                else:
                    planes, dirs = _slip.fcc_planes, _slip.fcc_dirs
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

        return self._to_grid(schmid)

    @map_property("CSL Boundaries", dtype="rgb", category="microstructure")
    def csl_boundary_map(self) -> np.ndarray:
        sym_quats = self._primary_symmetry_quats()
        topo = self.topology
        rgb = np.ones((topo.n_pixels, 3), dtype=np.float64)
        _csl = CSLParams()

        sigma3_axis = np.array(_csl.sigma3_axis, dtype=np.float64)
        sigma3_axis /= np.linalg.norm(sigma3_axis)
        sigma9_axis = np.array(_csl.sigma9_axis, dtype=np.float64)
        sigma9_axis /= np.linalg.norm(sigma9_axis)

        quats = self.quaternions
        for k in range(topo.pairs.shape[0]):
            i, j = int(topo.pairs[k, 0]), int(topo.pairs[k, 1])
            angle, axis = MisorientationOps.axis_angle_pair(
                quats[i], quats[j], sym_quats
            )
            color = self._classify_csl(
                angle,
                axis,
                _csl.sigma3_angle,
                sigma3_axis,
                _csl.sigma3_tolerance,
                _csl.sigma9_angle,
                sigma9_axis,
                _csl.sigma9_tolerance,
                _csl.axis_dot_threshold,
                _csl.low_angle_threshold,
                _csl.high_angle_threshold,
            )
            rgb[i] = color
            rgb[j] = color

        return self._to_grid(rgb)

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
        dot_threshold: float = 0.9,
        low_angle: float = 2.0,
        high_angle: float = 15.0,
    ) -> np.ndarray:
        if angle < low_angle:
            return np.array([0.7, 0.7, 0.7])
        if angle < high_angle:
            return np.array([0.5, 0.5, 0.5])
        axis_norm = np.linalg.norm(axis)
        if axis_norm < 1e-10:
            return np.array([0.0, 0.0, 0.0])
        axis_unit = axis / axis_norm
        if (
            abs(angle - s3_angle) < s3_tol
            and abs(np.dot(axis_unit, s3_axis)) > dot_threshold
        ):
            return np.array([1.0, 0.0, 0.0])
        if (
            abs(angle - s9_angle) < s9_tol
            and abs(np.dot(axis_unit, s9_axis)) > dot_threshold
        ):
            return np.array([0.0, 0.0, 1.0])
        return np.array([0.0, 0.0, 0.0])
