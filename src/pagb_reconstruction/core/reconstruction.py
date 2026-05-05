from typing import Literal

import numpy as np
from orix.quaternion import Orientation
from pydantic import Field
from scipy.optimize import minimize

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.grain import Grain, detect_grains
from pagb_reconstruction.core.graph import (
    build_adjacency_graph,
    build_variant_graph,
    markov_cluster,
    variant_graph_cluster,
    vote_fill,
)
from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.utils.array_ops import (
    align_hemisphere,
    grain_index_map,
    remap_labels,
)
from pagb_reconstruction.utils.math_ops import MisorientationOps, QuaternionOps


class ReconstructionConfig(Displayable):
    algorithm: Literal["grain_graph", "variant_graph"] = Field(
        default="variant_graph",
        description="Reconstruction algorithm: variant_graph (recommended) or grain_graph",
    )
    or_type: str = Field(
        default="KS",
        description="Orientation relationship preset name (KS, NW, GT, Pitsch, Bain)",
    )
    optimize_or: bool = Field(
        default=True,
        description="Iteratively refine the OR to minimize mean fit angle",
    )
    threshold_deg: float = Field(
        default=2.5,
        description="Maximum misorientation (°) for graph edge creation between neighboring grains",
    )
    tolerance_deg: float = Field(
        default=2.5,
        description="Gaussian tolerance (°) for edge weight decay beyond threshold",
    )
    inflation_power: float = Field(
        default=1.6,
        description="MCL inflation exponent controlling cluster granularity (higher = more clusters)",
    )
    grain_threshold_deg: float = Field(
        default=5.0,
        description="Misorientation threshold (°) for child grain boundary detection",
    )
    min_grain_size: int = Field(
        default=5,
        description="Minimum grain size in pixels; smaller regions are discarded",
    )
    revert_threshold_deg: float = Field(
        default=5.0,
        description="Maximum fit angle (°) before reverting a grain to unclustered",
    )
    merge_similar_deg: float = Field(
        default=7.0,
        description="Parent grains within this misorientation (°) are merged",
    )
    merge_inclusions_max_size: int = Field(
        default=50,
        description="Parent clusters smaller than this (total pixels) are merged into neighbors",
    )
    n_vote_iterations: int = Field(
        default=3,
        description="Number of neighbor-voting iterations for filling unlabeled grains",
    )
    min_cluster_size: int = Field(
        default=15,
        description="Minimum parent cluster size; smaller clusters are reassigned",
    )


class ReconstructionResult(Displayable):
    parent_orientations: np.ndarray
    parent_grain_ids: np.ndarray
    fit_angles: np.ndarray
    variant_ids: np.ndarray
    packet_ids: np.ndarray
    block_ids: np.ndarray
    bain_ids: np.ndarray
    optimized_or: OrientationRelationship | None = None


def _axis_angle_to_rotation(ax_vec: np.ndarray) -> np.ndarray:
    ax_norm = np.linalg.norm(ax_vec)
    if ax_norm < 1e-10:
        return np.eye(3)
    ax = ax_vec / ax_norm
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + np.sin(ax_norm) * K + (1 - np.cos(ax_norm)) * (K @ K)


def _generate_variants_numpy(R: np.ndarray, parent_sym_quats: np.ndarray) -> np.ndarray:
    or_q = QuaternionOps.from_rotation_matrix(R)
    n_sym = parent_sym_quats.shape[0]
    raw = np.empty((n_sym, 4))
    for i in range(n_sym):
        v = QuaternionOps.multiply(parent_sym_quats[i], or_q)
        if v[0] < 0:
            v = -v
        raw[i] = v
    _, idx = np.unique(np.round(raw, 4), axis=0, return_index=True)
    return raw[np.sort(idx)]


class ReconstructionEngine:
    def __init__(self, ebsd_map: EBSDMap, config: ReconstructionConfig):
        self._map = ebsd_map
        self._config = config
        self._or: OrientationRelationship | None = None
        self._grains: list[Grain] = []
        self._parent_labels: np.ndarray = np.array([])
        self._parent_quats: np.ndarray = np.array([])

    def run(self, progress_callback=None) -> ReconstructionResult:
        def _progress(step: str, pct: float):
            if progress_callback:
                progress_callback(step, pct)

        _progress("Detecting grains", 0.0)
        self._grains = self._detect_grains()
        self._map.grains = self._grains

        _progress("Setting up OR", 0.15)
        self._or = self._get_or()

        if self._config.optimize_or:
            _progress("Refining OR", 0.2)
            self._or = self._refine_or(_progress)

        if self._config.algorithm == "variant_graph":
            return self._run_variant_graph(_progress)
        return self._run_grain_graph(_progress)

    def _run_variant_graph(self, _progress) -> ReconstructionResult:
        _progress("Building variant graph", 0.3)
        sym_quats = self._map._primary_symmetry_quats()
        adj, all_candidates = build_variant_graph(
            self._grains,
            self._or,
            sym_quats,
            threshold_deg=self._config.threshold_deg,
            tolerance_deg=self._config.tolerance_deg,
            progress_callback=_progress,
        )

        _progress("Clustering variants", 0.5)
        n_variants = self._or.n_variants
        parent_oris, best_variants, self._parent_labels = variant_graph_cluster(
            adj,
            all_candidates,
            len(self._grains),
            n_variants,
            inflation=self._config.inflation_power,
        )
        self._parent_quats = self._aggregate_parent_quats(parent_oris)

        _progress("Vote filling", 0.7)
        self._parent_labels = vote_fill(
            self._parent_labels, self._grains, self._config.n_vote_iterations
        )

        _progress("Merging similar", 0.8)
        self._merge_similar()

        _progress("Merging inclusions", 0.85)
        self._merge_inclusions()

        fit_angles = self._compute_fit_angles()

        _progress("Computing variants", 0.95)
        variant_ids, packet_ids, block_ids, bain_ids = self._compute_variants()

        _progress("Done", 1.0)
        return ReconstructionResult(
            parent_orientations=self._expand_to_pixels(self._parent_quats),
            parent_grain_ids=self._expand_labels_to_pixels(),
            fit_angles=fit_angles,
            variant_ids=variant_ids,
            packet_ids=packet_ids,
            block_ids=block_ids,
            bain_ids=bain_ids,
            optimized_or=self._or,
        )

    def _run_grain_graph(self, _progress) -> ReconstructionResult:
        _progress("Building graph", 0.3)
        adjacency = self._build_graph()

        _progress("Clustering", 0.5)
        self._parent_labels = markov_cluster(
            adjacency, inflation_power=self._config.inflation_power
        )

        _progress("Computing parent orientations", 0.65)
        self._parent_quats = self._compute_parent_orientations()

        _progress("Vote filling", 0.75)
        self._parent_labels = vote_fill(
            self._parent_labels, self._grains, self._config.n_vote_iterations
        )

        _progress("Merging similar", 0.85)
        self._merge_similar()

        _progress("Merging inclusions", 0.9)
        self._merge_inclusions()

        _progress("Computing variants", 0.95)
        variant_ids, packet_ids, block_ids, bain_ids = self._compute_variants()

        fit_angles = self._compute_fit_angles()

        _progress("Done", 1.0)
        return ReconstructionResult(
            parent_orientations=self._expand_to_pixels(self._parent_quats),
            parent_grain_ids=self._expand_labels_to_pixels(),
            fit_angles=fit_angles,
            variant_ids=variant_ids,
            packet_ids=packet_ids,
            block_ids=block_ids,
            bain_ids=bain_ids,
            optimized_or=self._or,
        )

    def _detect_grains(self) -> list[Grain]:
        sym_quats = self._map._primary_symmetry_quats()
        return detect_grains(
            quaternions=self._map.quaternions,
            phase_ids=self._map.phase_ids,
            topology=self._map.topology,
            symmetry_quats=sym_quats,
            threshold_deg=self._config.grain_threshold_deg,
            min_size=self._config.min_grain_size,
        )

    def _get_or(self) -> OrientationRelationship:
        preset_fn = OrientationRelationship.OR_PRESETS.get(self._config.or_type)
        if preset_fn:
            return preset_fn()
        return OrientationRelationship.kurdjumov_sachs()

    def _build_graph(self):
        or_misoris = self._or.theoretical_misorientations()
        sym_quats = self._map._primary_symmetry_quats()
        return build_adjacency_graph(
            self._grains,
            or_misoris,
            sym_quats,
            threshold_deg=self._config.threshold_deg,
            tolerance_deg=self._config.tolerance_deg,
        )

    def _aggregate_parent_quats(self, per_grain_parents: np.ndarray) -> np.ndarray:
        unique_labels = np.unique(self._parent_labels)
        parent_quats = np.zeros((len(unique_labels), 4))
        label_map = {l: idx for idx, l in enumerate(unique_labels)}

        for label in unique_labels:
            members = np.where(self._parent_labels == label)[0]
            qs = per_grain_parents[members]
            qs = align_hemisphere(qs, qs[0])
            mean_q = qs.mean(axis=0)
            norm = np.linalg.norm(mean_q)
            parent_quats[label_map[label]] = (
                mean_q / norm if norm > 1e-10 else np.array([1, 0, 0, 0])
            )

        self._parent_labels = remap_labels(self._parent_labels)
        return parent_quats

    def _refine_or(self, progress_callback=None) -> OrientationRelationship:
        if len(self._grains) < 2:
            return self._or

        grain_quats = np.array(
            [g.mean_quaternion for g in self._grains], dtype=np.float64
        )
        gid_map = grain_index_map(self._grains)
        pairs = []
        for grain in self._grains:
            for nid in grain.neighbor_ids:
                j = gid_map.get(nid)
                if j is not None and j > gid_map[grain.id]:
                    pairs.append((gid_map[grain.id], j))

        if not pairs:
            return self._or

        pair_arr = np.array(pairs, dtype=np.int32)

        max_pairs = 500
        if len(pair_arr) > max_pairs:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(pair_arr), max_pairs, replace=False)
            pair_arr = pair_arr[idx]

        pair_qi = np.ascontiguousarray(grain_quats[pair_arr[:, 0]])
        pair_qj = np.ascontiguousarray(grain_quats[pair_arr[:, 1]])

        base_R = self._or.rotation_matrix.copy()
        parent_sym_quats = np.asarray(
            self._or.parent_phase.symmetry.data, dtype=np.float64
        ).reshape(-1, 4)

        iteration_count = [0]

        def cost(params):
            delta_R = _axis_angle_to_rotation(params[:3])
            R_test = delta_R @ base_R
            test_variants = _generate_variants_numpy(R_test, parent_sym_quats)
            total = MisorientationOps.refine_or_cost(
                pair_qi, pair_qj, test_variants, parent_sym_quats
            )
            iteration_count[0] += 1
            if iteration_count[0] % 10 == 0 and progress_callback:
                frac = min(iteration_count[0] / 100, 1.0)
                progress_callback(
                    f"Refining OR (iter {iteration_count[0]})", 0.2 + frac * 0.1
                )
            return total

        initial_cost = cost(np.zeros(3))
        result = minimize(
            cost,
            x0=np.zeros(3),
            method="Nelder-Mead",
            options={"maxiter": 100, "xatol": 1e-3, "fatol": 1e-3},
        )

        if result.fun >= initial_cost:
            return self._or

        delta_R = _axis_angle_to_rotation(result.x)
        refined_R = delta_R @ base_R

        refined = self._or.model_copy()
        refined._rotation_matrix = refined_R
        return refined

    def _compute_parent_orientations(self) -> np.ndarray:
        unique_labels = np.unique(self._parent_labels)
        parent_quats = np.zeros((len(unique_labels), 4))

        for idx, label in enumerate(unique_labels):
            cluster_indices = np.where(self._parent_labels == label)[0]
            cluster_grains = [self._grains[i] for i in cluster_indices]

            all_candidates = []
            for grain in cluster_grains:
                candidates = self._or.candidate_parents(grain.mean_quaternion)
                all_candidates.append(candidates)

            if all_candidates:
                all_c = np.vstack(all_candidates)
                all_c = align_hemisphere(all_c, all_c[0])
                mean_q = all_c.mean(axis=0)
                norm = np.linalg.norm(mean_q)
                parent_quats[idx] = (
                    mean_q / norm if norm > 1e-10 else np.array([1, 0, 0, 0])
                )
            else:
                parent_quats[idx] = np.array([1, 0, 0, 0])

        return parent_quats

    def _merge_similar(self):
        if self._config.merge_similar_deg <= 0:
            return

        sym_quats = self._map._primary_symmetry_quats()
        unique_labels = np.unique(self._parent_labels)
        n = len(unique_labels)

        merge_map = {l: l for l in unique_labels}

        def _find_root(label):
            while merge_map[label] != label:
                merge_map[label] = merge_map[merge_map[label]]
                label = merge_map[label]
            return label

        for i in range(n):
            for j in range(i + 1, n):
                li, lj = unique_labels[i], unique_labels[j]
                if li >= len(self._parent_quats) or lj >= len(self._parent_quats):
                    continue
                angle = MisorientationOps.pair(
                    self._parent_quats[li], self._parent_quats[lj], sym_quats
                )
                if angle < self._config.merge_similar_deg:
                    ri, rj = _find_root(li), _find_root(lj)
                    if ri != rj:
                        merge_map[rj] = ri

        for i in range(len(self._parent_labels)):
            self._parent_labels[i] = _find_root(self._parent_labels[i])

    def _merge_inclusions(self):
        if self._config.merge_inclusions_max_size <= 0:
            return
        grain_id_to_idx = grain_index_map(self._grains)
        unique_labels = np.unique(self._parent_labels)
        for label in unique_labels:
            indices = np.where(self._parent_labels == label)[0]
            total_size = sum(
                self._grains[i].area for i in indices if i < len(self._grains)
            )
            if total_size < self._config.merge_inclusions_max_size:
                neighbor_labels = set()
                for i in indices:
                    if i < len(self._grains):
                        for nid in self._grains[i].neighbor_ids:
                            j = grain_id_to_idx.get(nid)
                            if j is not None and self._parent_labels[j] != label:
                                neighbor_labels.add(self._parent_labels[j])
                if neighbor_labels:
                    self._parent_labels[indices] = next(iter(neighbor_labels))

    def _compute_variants(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n_pixels = self._map.quaternions.shape[0]
        variant_ids = np.zeros(n_pixels, dtype=np.int32)
        packet_ids = np.zeros(n_pixels, dtype=np.int32)
        block_ids = np.zeros(n_pixels, dtype=np.int32)
        bain_ids = np.zeros(n_pixels, dtype=np.int32)

        variants = self._or.variant_quaternions()
        n_variants = len(variants)

        for grain_idx, grain in enumerate(self._grains):
            parent_label = (
                self._parent_labels[grain_idx]
                if grain_idx < len(self._parent_labels)
                else 0
            )
            if parent_label >= len(self._parent_quats):
                continue
            parent_q = self._parent_quats[parent_label]

            child_q = grain.mean_quaternion
            child_ori = Orientation(child_q.reshape(1, 4))
            parent_ori = Orientation(parent_q.reshape(1, 4))

            best_variant = 0
            best_angle = 999.0

            for v_idx, v_q in enumerate(variants):
                v_ori = Orientation(v_q.reshape(1, 4))
                predicted_child = parent_ori * v_ori
                mori = (~predicted_child) * child_ori
                angle = float(np.abs(mori.angle.data[0])) * 180.0 / np.pi
                if angle < best_angle:
                    best_angle = angle
                    best_variant = v_idx

            variant_ids[grain.pixel_indices] = best_variant
            variants_per_packet = max(n_variants // 4, 1)
            n_bain = min(n_variants, 3)
            packet_ids[grain.pixel_indices] = best_variant // variants_per_packet
            block_ids[grain.pixel_indices] = best_variant // 2
            bain_ids[grain.pixel_indices] = best_variant % n_bain

        return variant_ids, packet_ids, block_ids, bain_ids

    def _compute_fit_angles(self) -> np.ndarray:
        n_pixels = self._map.quaternions.shape[0]
        fit = np.full(n_pixels, np.nan)
        sym_quats = self._map._primary_symmetry_quats()

        for grain_idx, grain in enumerate(self._grains):
            parent_label = (
                self._parent_labels[grain_idx]
                if grain_idx < len(self._parent_labels)
                else 0
            )
            if parent_label >= len(self._parent_quats):
                continue
            parent_q = self._parent_quats[parent_label]
            candidates = self._or.candidate_parents(grain.mean_quaternion)
            if len(candidates) == 0:
                continue
            deviations = [
                MisorientationOps.pair(c, parent_q, sym_quats) for c in candidates
            ]
            fit[grain.pixel_indices] = np.min(deviations)

        return fit

    def _expand_to_pixels(self, parent_quats: np.ndarray) -> np.ndarray:
        n_pixels = self._map.quaternions.shape[0]
        result = np.zeros((n_pixels, 4))
        result[:, 0] = 1.0

        for i, grain in enumerate(self._grains):
            if i >= len(self._parent_labels):
                continue
            label = self._parent_labels[i]
            if label < len(parent_quats):
                result[grain.pixel_indices] = parent_quats[label]

        return result

    def _expand_labels_to_pixels(self) -> np.ndarray:
        n_pixels = self._map.quaternions.shape[0]
        result = np.full(n_pixels, -1, dtype=np.int32)

        for i, grain in enumerate(self._grains):
            if i >= len(self._parent_labels):
                continue
            result[grain.pixel_indices] = self._parent_labels[i]

        return result
