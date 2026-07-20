from typing import Literal

import numpy as np
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
    grain_index_map,
    remap_labels,
)
from pagb_reconstruction.utils.compute import Quaternions
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
    fill_nonindexed: bool = Field(
        default=False,
        title="Fill non-indexed pixels",
        description="Fill non-indexed pixels from their nearest indexed neighbour "
        "BEFORE reconstruction — stops lath/sheaf-boundary noise from splitting "
        "prior-austenite grains into islands (Taylor et al. 2024).",
    )
    grain_threshold_deg: float = Field(
        default=5.0,
        description="Misorientation threshold (°) for child grain boundary detection",
    )
    min_grain_size: int = Field(
        default=5,
        title="Min. child grain (px)",
        description="Minimum child (martensite/bainite) grain size in pixels during "
        "grain detection; smaller regions are discarded as noise before clustering",
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
        title="Merge islands ≤ (px)",
        description="Parent clusters smaller than this (total pixels) are merged into neighbors",
    )
    n_vote_iterations: int = Field(
        default=3,
        description="Number of neighbor-voting iterations for filling unlabeled grains",
    )
    min_cluster_size: int = Field(
        default=1,
        ge=1,
        le=200,
        title="Min. cluster size (grains)",
        description="Minimum child grains per parent cluster; smaller clusters are "
        "reverted to unreconstructed. 1 = off (Niessen et al. 2022 use 15 on large "
        "maps). Raise to drop under-sampled clusters.",
    )
    min_parent_size_um: float = Field(
        default=0.0,
        ge=0.0,
        le=50.0,
        title="Min. parent grain size (µm)",
        description="Removes reconstructed parent grains smaller than this (µm "
        "equivalent circle diameter) — the noise islands. 0 = off. Prior austenite "
        "is typically 15–50 µm (Cayron 2006; Taylor et al. 2024).",
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

        _progress("Removing noise islands", 0.9)
        self._prune_noise()

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

        _progress("Removing noise islands", 0.93)
        self._prune_noise()

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
        if self._config.fill_nonindexed:
            quaternions, phase_ids = self._map.filled_pixel_data()
        else:
            quaternions, phase_ids = self._map.quaternions, self._map.phase_ids
        return detect_grains(
            quaternions=quaternions,
            phase_ids=phase_ids,
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

    def _parent_symmetry_quats(self) -> np.ndarray:
        return np.asarray(
            self._or.parent_phase.symmetry.data, dtype=np.float64
        ).reshape(-1, 4)

    def _aggregate_parent_quats(self, per_grain_parents: np.ndarray) -> np.ndarray:
        unique_labels = np.unique(self._parent_labels)
        parent_quats = np.zeros((len(unique_labels), 4))
        label_map = {l: idx for idx, l in enumerate(unique_labels)}
        sym = self._parent_symmetry_quats()

        for label in unique_labels:
            members = np.where(self._parent_labels == label)[0]
            qs = np.ascontiguousarray(per_grain_parents[members], dtype=np.float64)
            parent_quats[label_map[label]] = QuaternionOps.symmetric_mean(qs, sym)

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
                all_c = np.ascontiguousarray(np.vstack(all_candidates), dtype=np.float64)
                parent_quats[idx] = QuaternionOps.symmetric_mean(
                    all_c, self._parent_symmetry_quats()
                )
            else:
                parent_quats[idx] = np.array([1, 0, 0, 0])

        return parent_quats

    def _merge_similar(self):
        if self._config.merge_similar_deg <= 0:
            return

        sym_quats = self._map._primary_symmetry_quats()
        labels = self._parent_labels
        n_parents = len(self._parent_quats)

        merge_map = {int(l): int(l) for l in np.unique(labels)}

        def _find_root(label):
            label = int(label)
            while merge_map[label] != label:
                merge_map[label] = merge_map[merge_map[label]]
                label = merge_map[label]
            return label

        # Merge parents within merge_similar_deg ONLY when spatially ADJACENT (a
        # grain of one neighbours a grain of the other). Merging globally-similar
        # but distant parents fuses unrelated prior-austenite grains into giant
        # blobs — 98% "reconstructed" as one over-merged grain, high fit, nothing
        # visible (issue #9). A chain of adjacent-similar parents still merges
        # transitively (a real grain the initial clustering split).
        id_to_idx = grain_index_map(self._grains)
        adj_pairs: set[tuple[int, int]] = set()
        for i, grain in enumerate(self._grains):
            li = int(labels[i]) if i < len(labels) else -1
            if not 0 <= li < n_parents:
                continue
            for nid in grain.neighbor_ids:
                j = id_to_idx.get(nid)
                if j is None or j >= len(labels):
                    continue
                lj = int(labels[j])
                if lj != li and 0 <= lj < n_parents:
                    adj_pairs.add((min(li, lj), max(li, lj)))

        if adj_pairs:
            pairs = np.array(sorted(adj_pairs))
            angles = Quaternions.disorientation_deg(
                self._parent_quats[pairs[:, 0]], self._parent_quats[pairs[:, 1]], sym_quats
            )
            for (li, lj), ang in zip(pairs, angles):
                if ang < self._config.merge_similar_deg:
                    ri, rj = _find_root(li), _find_root(lj)
                    if ri != rj:
                        merge_map[rj] = ri

        for i in range(len(labels)):
            labels[i] = _find_root(labels[i])

    def _merge_inclusions(self):
        if self._config.merge_inclusions_max_size <= 0:
            return
        grain_id_to_idx = grain_index_map(self._grains)
        labels = self._parent_labels
        n_grains = len(self._grains)
        # Pull grain fields into plain arrays/lists once — repeated pydantic
        # attribute access per grain per label dominated this pass.
        areas = np.array([g.area for g in self._grains], dtype=np.int64)
        neighbor_ids = [g.neighbor_ids for g in self._grains]
        for label in np.unique(labels):
            indices = np.where(labels == label)[0]
            in_grains = indices[indices < n_grains]
            if areas[in_grains].sum() < self._config.merge_inclusions_max_size:
                neighbor_labels = set()
                for i in in_grains:
                    for nid in neighbor_ids[i]:
                        j = grain_id_to_idx.get(nid)
                        if j is not None and labels[j] != label:
                            neighbor_labels.add(labels[j])
                if neighbor_labels:
                    labels[indices] = next(iter(neighbor_labels))

    def _prune_noise(self):
        """Drop noise: revert under-sized clusters, then remove sub-µm parent
        islands. Shared post-clustering step for both reconstruction algorithms."""
        self._revert_small_clusters()
        self._remove_small_parents()

    def _revert_small_clusters(self):
        """Revert parent clusters with fewer than ``min_cluster_size`` child
        grains to unreconstructed (label -1). Wires the previously-inert
        ``min_cluster_size`` field (Niessen et al. 2022, clusterSize revert)."""
        if self._config.min_cluster_size <= 1:
            return
        labels = self._parent_labels
        mask = labels >= 0
        if not mask.any():
            return
        counts = np.bincount(labels[mask])
        small = np.where(counts < self._config.min_cluster_size)[0]
        if small.size:
            labels[np.isin(labels, small)] = -1

    def _remove_small_parents(self):
        """Remove reconstructed parent grains whose equivalent circle diameter is
        below ``min_parent_size_um`` — the tiny noise islands prior-austenite
        reconstruction leaves behind (real PAGs are ~15–50 µm). Their pixels
        become unreconstructed (label -1)."""
        if self._config.min_parent_size_um <= 0:
            return
        labels = self._parent_labels
        mask = labels >= 0
        if not mask.any():
            return
        dy_um, dx_um = self._map.step_size
        px_area = dx_um * dy_um
        n_labels = int(labels[mask].max()) + 1
        area_px = np.zeros(n_labels)
        for i in range(min(len(labels), len(self._grains))):
            label = labels[i]
            if label >= 0:
                area_px[label] += self._grains[i].area
        ecd_um = 2.0 * np.sqrt(area_px * px_area / np.pi)
        small = np.where(ecd_um < self._config.min_parent_size_um)[0]
        if small.size:
            labels[np.isin(labels, small)] = -1

    def _grain_parent_child(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Per-grain (parent_q, child_q, valid) arrays for the vectorised
        variant/fit passes. ``valid`` is False for grains with no assigned
        parent (unreconstructed / out-of-range label)."""
        n = len(self._grains)
        parent = np.zeros((n, 4))
        child = np.zeros((n, 4))
        valid = np.zeros(n, dtype=bool)
        pl, pq = self._parent_labels, self._parent_quats
        for i, grain in enumerate(self._grains):
            label = pl[i] if i < len(pl) else -1
            if 0 <= label < len(pq):
                parent[i] = pq[label]
                child[i] = grain.mean_quaternion
                valid[i] = True
        return parent, child, valid

    def _compute_variants(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n_pixels = self._map.quaternions.shape[0]
        variant_ids = np.zeros(n_pixels, dtype=np.int32)
        packet_ids = np.zeros(n_pixels, dtype=np.int32)
        block_ids = np.zeros(n_pixels, dtype=np.int32)
        bain_ids = np.zeros(n_pixels, dtype=np.int32)

        variants = self._or.variant_quaternions()  # (K, 4)
        n_variants = len(variants)
        parent, child, valid = self._grain_parent_child()

        # Best variant per grain on the compute device (GPU when available):
        # predicted child = variant ∘ parent, then the variant minimising the
        # disorientation to the measured child.
        best = Quaternions.best_variant(variants, parent, child)

        variants_per_packet = max(n_variants // 4, 1)
        n_bain = min(n_variants, 3)
        for i, grain in enumerate(self._grains):
            if not valid[i]:
                continue
            b = int(best[i])
            variant_ids[grain.pixel_indices] = b
            packet_ids[grain.pixel_indices] = b // variants_per_packet
            block_ids[grain.pixel_indices] = b // 2
            bain_ids[grain.pixel_indices] = b % n_bain

        return variant_ids, packet_ids, block_ids, bain_ids

    def _compute_fit_angles(self) -> np.ndarray:
        n_pixels = self._map.quaternions.shape[0]
        fit = np.full(n_pixels, np.nan)
        sym_quats = self._map._primary_symmetry_quats()

        variants = self._or.variant_quaternions()  # (K, 4)
        parent, child, valid = self._grain_parent_child()

        # Candidate parents' closest disorientation to the assigned parent, on
        # the compute device (GPU when available) — the per-grain fit angle.
        fit_per_grain = Quaternions.fit_angles(variants, parent, child, sym_quats)

        for i, grain in enumerate(self._grains):
            if valid[i]:
                fit[grain.pixel_indices] = fit_per_grain[i]

        return fit

    def _expand_to_pixels(self, parent_quats: np.ndarray) -> np.ndarray:
        n_pixels = self._map.quaternions.shape[0]
        result = np.zeros((n_pixels, 4))
        result[:, 0] = 1.0

        for i, grain in enumerate(self._grains):
            if i >= len(self._parent_labels):
                continue
            label = self._parent_labels[i]
            if 0 <= label < len(parent_quats):
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
