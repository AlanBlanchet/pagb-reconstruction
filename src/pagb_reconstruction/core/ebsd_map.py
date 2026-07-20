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
from pagb_reconstruction.utils.compute import Quaternions
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

    def phase_by_id(self, phase_id: int) -> PhaseConfig | None:
        """Look up a phase by its EBSD phase id (NOT its list position; orix
        phase ids are not 0-based list indices)."""
        for phase in self.phases:
            if phase.phase_id == phase_id:
                return phase
        return None

    def phase_name(self, phase_id: int) -> str:
        phase = self.phase_by_id(phase_id)
        return phase.name if phase is not None else "?"

    @property
    def is_sparse(self) -> bool:
        rows, cols = self.shape
        return self.crystal_map.size != rows * cols

    @property
    def indexed_grid_mask(self) -> np.ndarray:
        """Grid-shaped bool mask: True where a measured, indexed point exists
        (present in the crystal map AND phase_id >= 0). Non-indexed points —
        absent from a sparse map, or phase -1 in a dense one — are False."""
        ok = self._to_grid((self.crystal_map.phase_id >= 0).astype(np.uint8))
        return ok.astype(bool)

    def _fill_unindexed(self, grid: np.ndarray) -> np.ndarray:
        """DISPLAY cleanup: paint non-indexed points with their nearest indexed
        neighbour's value (the standard EBSD map clean-up). Scan data is never
        modified — only the rendered map; a scan with no indexed point at all
        is returned unchanged."""
        mask = self.indexed_grid_mask
        if mask.all() or not mask.any():
            return grid
        from scipy.ndimage import distance_transform_edt

        idx = distance_transform_edt(~mask, return_distances=False, return_indices=True)
        return grid[tuple(idx)]

    def filled_pixel_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Quaternions + phase ids with every non-indexed pixel replaced by its
        nearest indexed neighbour, in pixel order — for cleaning BEFORE
        reconstruction. Taylor et al. 2024: non-indexed pixels at lath/sheaf
        boundaries otherwise split prior-austenite grains into islands, and
        filling before beats cleaning after. No-op (returns the raw data) for a
        sparse map, or an all-/none-indexed map, where nearest-neighbour fill in
        pixel-grid order is undefined."""
        q = self.quaternions
        ph = self.phase_ids
        mask = self.indexed_grid_mask
        if self.is_sparse or mask.all() or not mask.any():
            return q, ph
        from scipy.ndimage import distance_transform_edt

        idx = distance_transform_edt(
            ~mask, return_distances=False, return_indices=True
        )
        rows, cols = self.shape
        q_filled = q.reshape(rows, cols, 4)[tuple(idx)].reshape(-1, 4)
        ph_filled = ph.reshape(rows, cols)[tuple(idx)].reshape(-1)
        return q_filled, ph_filled

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

    @map_property("Phase", dtype="rgb", category="phase")
    def phase_map(self) -> np.ndarray:
        phase_ids = self.crystal_map.phase_id
        rgb = np.zeros((len(phase_ids), 3), dtype=np.float32)
        for phase in self.phases:
            mask = phase_ids == phase.phase_id
            color = matplotlib.colors.to_rgb(phase.color)
            rgb[mask] = color
        return self._fill_unindexed(self._to_grid(rgb))

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
        return self._fill_unindexed(self._to_grid(rgb))

    @map_property("Euler Angles", dtype="rgb", category="orientation")
    def euler_angle_map(self) -> np.ndarray:
        euler = self.crystal_map.rotations.to_euler(degrees=True)
        return self._fill_unindexed(self._to_grid(euler))

    @map_property("Grain ID", dtype="discrete", category="microstructure")
    def grain_id_map(self) -> np.ndarray:
        gmap = np.zeros(self.topology.n_pixels, dtype=np.float32)
        grains = self.require_grains()
        if not grains:
            return self._to_grid(gmap)
        for g in grains:
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

    def primary_symmetry(self):
        """orix point-group Symmetry of the first indexed phase (for IPF keys)."""
        phases = self.crystal_map.phases_in_data
        for pid in phases.ids:
            if pid >= 0 and phases[pid].point_group is not None:
                return phases[pid].point_group
        raise ValueError("No indexed phase with point group found")

    def _primary_symmetry_quats(self) -> np.ndarray:
        return self.primary_symmetry().data

    def _pair_angles(self):
        topo = self.topology
        angles = MisorientationOps.pairs(
            self.quaternions, topo.pairs, self._primary_symmetry_quats()
        )
        return topo, angles

    def misorientation_angles(self) -> np.ndarray:
        """Disorientation angle (deg) for every neighbouring-pixel pair — the
        misorientation angle distribution. Distinct from reconstruction fit."""
        return self._pair_angles()[1]

    def _pixel_kam(self) -> np.ndarray:
        """Per-pixel Kernel Average Misorientation in pixel-index space."""
        topo, angles = self._pair_angles()
        kam = np.zeros(topo.n_pixels, dtype=np.float64)
        np.add.at(kam, topo.pairs[:, 0], angles)
        np.add.at(kam, topo.pairs[:, 1], angles)
        return kam / np.maximum(topo.degree, 1)

    @map_property(
        "KAM", dtype="scalar", unit="\u00b0", colormap="inferno", category="deformation"
    )
    def kam_map(self) -> np.ndarray:
        return self._to_grid(self._pixel_kam())

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
        "Fit Angle",
        requires_result=True,
        dtype="scalar",
        unit="\u00b0",
        colormap="hot",
        category="reconstruction",
    )
    def fit_angle_map(self) -> np.ndarray:
        return self._to_grid(self._result.fit_angles, fill=np.nan)

    @map_property(
        "Packet", requires_result=True, dtype="discrete", category="reconstruction"
    )
    def packet_map(self) -> np.ndarray:
        return self._to_grid(self._result.packet_ids).astype(np.float32)

    @map_property(
        "Block", requires_result=True, dtype="discrete", category="reconstruction"
    )
    def block_map(self) -> np.ndarray:
        return self._to_grid(self._result.block_ids).astype(np.float32)

    @map_property(
        "Parent IPF", requires_result=True, dtype="rgb", category="reconstruction"
    )
    def parent_ipf_map(self) -> np.ndarray:
        parent_quats = self._result.parent_orientations
        parent_ids = self._to_grid(self._result.parent_grain_ids, fill=-1)
        reconstructed = parent_ids >= 0
        phases = self.crystal_map.phases_in_data
        sym = None
        for pid in phases.ids:
            if pid >= 0 and phases[pid].point_group is not None:
                sym = phases[pid].point_group
                break

        # Unreconstructed pixels are neutral grey (never black), so a partial
        # or empty reconstruction reads honestly instead of a blank frame
        # (issue #9: "98% reconstructed but I see nothing").
        rgb = np.full((*self.shape, 3), 0.18)
        if sym is not None:
            ori = Orientation(parent_quats.reshape(-1, 4), symmetry=sym)
            colors = self._to_grid(IPFColorKeyTSL(sym, direction=Vector3d.zvector())
                                    .orientation2color(ori))
            rgb[reconstructed] = colors[reconstructed]
        else:
            # No crystal symmetry to build an IPF key — fall back to distinct
            # per-grain colours so the grains stay VISIBLE, never an all-black map.
            cmap = matplotlib.colormaps["tab20"]
            for i, gid in enumerate(np.unique(parent_ids[reconstructed])):
                rgb[parent_ids == gid] = cmap(i % 20)[:3]

        rgb[boundaries_from_2d(parent_ids)] = 0.1
        return rgb

    @map_property(
        "Parent + Boundaries",
        requires_result=True,
        dtype="rgb",
        category="reconstruction",
    )
    def parent_boundary_map(self) -> np.ndarray:
        parent_ids = self._to_grid(self._result.parent_grain_ids, fill=-1)
        cmap = matplotlib.colormaps["tab20"]
        # Unreconstructed pixels (id < 0) stay a NEUTRAL grey — colouring them
        # from the palette painted a near-empty result as one giant fake grain.
        rgb = np.full((*self.shape, 3), 0.18)
        for i, gid in enumerate(np.unique(parent_ids[parent_ids >= 0])):
            rgb[parent_ids == gid] = cmap(i % 20)[:3]
        boundary = boundaries_from_2d(parent_ids)
        rgb[boundary] = 0.0
        return rgb

    @map_property(
        "GOS", dtype="scalar", unit="\u00b0", colormap="hot", category="deformation"
    )
    def gos_map(self) -> np.ndarray:
        gos = np.zeros(self.topology.n_pixels, dtype=np.float64)
        grains = self.require_grains()
        if not grains:
            return self._to_grid(gos)
        _, deviation = self._grain_mean_deviation(grains)
        start = 0
        for g in grains:
            n = len(g.pixel_indices)
            if n:
                gos[g.pixel_indices] = deviation[start : start + n].mean()
            start += n
        return self._to_grid(gos)

    @map_property(
        "GAM",
        dtype="scalar",
        unit="°",
        colormap="inferno",
        category="deformation",
    )
    def gam_map(self) -> np.ndarray:
        """Grain Average Misorientation — per-grain mean of pixel KAM values."""
        kam = self._pixel_kam()
        gam = np.zeros_like(kam)
        for g in self.require_grains():
            if len(g.pixel_indices) == 0:
                continue
            gam[g.pixel_indices] = float(kam[g.pixel_indices].mean())
        return self._to_grid(gam)

    @map_property(
        "Misfit Boundaries",
        requires_result=True,
        dtype="rgb",
        category="reconstruction",
    )
    def misfit_boundaries_map(self) -> np.ndarray:
        bc = self.band_contrast_map()
        if np.any(bc):
            bc_norm = bc.astype(np.float64)
            vmin, vmax = float(np.nanmin(bc_norm)), float(np.nanmax(bc_norm))
            if vmax > vmin:
                bc_norm = (bc_norm - vmin) / (vmax - vmin)
            else:
                bc_norm = np.zeros_like(bc_norm)
            gray = 0.15 + 0.55 * bc_norm
        else:
            gray = np.full(self.shape, 0.18, dtype=np.float64)
        rgb = np.stack([gray, gray, gray], axis=-1)

        parent_ids = self._to_grid(self._result.parent_grain_ids, fill=-1)
        boundary = boundaries_from_2d(parent_ids)
        if not np.any(boundary):
            return rgb

        fit_grid = self._to_grid(self._result.fit_angles, fill=np.nan)
        local = np.where(np.isnan(fit_grid), 0.0, fit_grid)
        max_local = local.copy()
        max_local[:, :-1] = np.maximum(max_local[:, :-1], local[:, 1:])
        max_local[:, 1:] = np.maximum(max_local[:, 1:], local[:, :-1])
        max_local[:-1, :] = np.maximum(max_local[:-1, :], local[1:, :])
        max_local[1:, :] = np.maximum(max_local[1:, :], local[:-1, :])

        cmap = matplotlib.colormaps["RdYlGn_r"]
        vals = np.clip(max_local[boundary] / 10.0, 0.0, 1.0)
        colors = cmap(vals)[:, :3]
        rgb[boundary] = colors
        return rgb

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

    def _grain_mean_deviation(self, grains: list[Grain]) -> tuple[np.ndarray, np.ndarray]:
        """Disorientation of every grain pixel from its own grain's mean.

        ONE batched call through the compute backend (GPU when available). Doing
        this per pixel in Python took minutes on a full map.
        """
        pixels = np.concatenate([g.pixel_indices for g in grains])
        means = np.repeat(
            np.array([g.mean_quaternion for g in grains], dtype=np.float64),
            [len(g.pixel_indices) for g in grains],
            axis=0,
        )
        angles = Quaternions.disorientation_deg(
            self.quaternions[pixels], means, self._primary_symmetry_quats()
        )
        return pixels, angles

    def require_grains(self) -> list[Grain]:
        """Grains, detecting them on demand.

        Grain-based maps (Grain ID, GOS, GAM, GROD) are meaningless without them.
        Each used to guard separately, inconsistently: two returned an all-zero
        map that looked like real data, and one crashed iterating ``None``.
        """
        if not self.grains:
            self.run_grain_detection()
        return self.grains or []

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
        grains = self.require_grains()
        if not grains:
            return np.zeros(self.shape, dtype=np.float64)
        grod = np.zeros(self.topology.n_pixels, dtype=np.float64)
        pixels, deviation = self._grain_mean_deviation(grains)
        grod[pixels] = deviation
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

    @map_property(
        "Parent Grain Colors",
        requires_result=True,
        dtype="rgb",
        category="reconstruction",
    )
    def parent_grain_colors_map(self) -> np.ndarray:
        parent_ids = self._result.parent_grain_ids
        unique_ids = np.unique(parent_ids[parent_ids >= 0])
        n = len(unique_ids)
        golden_ratio = 0.618033988749895
        rgb = np.zeros((self.topology.n_pixels, 3), dtype=np.float64)
        for i, gid in enumerate(unique_ids):
            hue = (i * golden_ratio) % 1.0
            r, g, b = self._hsv_to_rgb(hue, 0.75, 0.9)
            rgb[parent_ids == gid] = [r, g, b]
        return self._to_grid(rgb)

    @staticmethod
    def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
        i = int(h * 6.0)
        f = h * 6.0 - i
        p = v * (1.0 - s)
        q = v * (1.0 - f * s)
        t = v * (1.0 - (1.0 - f) * s)
        i = i % 6
        if i == 0:
            return v, t, p
        if i == 1:
            return q, v, p
        if i == 2:
            return p, v, t
        if i == 3:
            return p, q, v
        if i == 4:
            return t, p, v
        return v, p, q
