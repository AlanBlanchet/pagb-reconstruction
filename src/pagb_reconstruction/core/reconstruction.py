from typing import Literal

import numpy as np
from orix.quaternion import Orientation
from pydantic import ConfigDict

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.grain import Grain, detect_grains
from pagb_reconstruction.core.graph import (
    build_adjacency_graph,
    markov_cluster,
    vote_fill,
)
from pagb_reconstruction.core.orientation_relationship import OrientationRelationship


class ReconstructionConfig(Displayable):
    algorithm: Literal["graph", "variant_graph"] = "graph"
    or_type: str = "KS"
    optimize_or: bool = True

    threshold_deg: float = 2.5
    tolerance_deg: float = 2.5
    inflation_power: float = 1.6

    grain_threshold_deg: float = 5.0
    min_grain_size: int = 5

    revert_threshold_deg: float = 5.0
    merge_similar_deg: float = 7.0
    merge_inclusions_max_size: int = 50
    n_vote_iterations: int = 3
    min_cluster_size: int = 15


class ReconstructionResult(Displayable):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parent_orientations: np.ndarray
    parent_grain_ids: np.ndarray
    fit_angles: np.ndarray
    variant_ids: np.ndarray
    packet_ids: np.ndarray
    bain_ids: np.ndarray
    optimized_or: OrientationRelationship | None = None


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

        _progress("Setting up OR", 0.15)
        self._or = self._get_or()

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
        variant_ids, packet_ids, bain_ids = self._compute_variants()

        fit_angles = self._compute_fit_angles()

        _progress("Done", 1.0)

        parent_orientations = self._expand_to_pixels(self._parent_quats)
        parent_grain_ids = self._expand_labels_to_pixels()

        return ReconstructionResult(
            parent_orientations=parent_orientations,
            parent_grain_ids=parent_grain_ids,
            fit_angles=fit_angles,
            variant_ids=variant_ids,
            packet_ids=packet_ids,
            bain_ids=bain_ids,
            optimized_or=self._or,
        )

    def _detect_grains(self) -> list[Grain]:
        sym_quats = self._map._primary_symmetry_quats()
        return detect_grains(
            quaternions=self._map.quaternions,
            phase_ids=self._map.phase_ids,
            shape=self._map.shape,
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
                # Normalize quaternions to same hemisphere before averaging
                reference = all_c[0]
                for k in range(1, len(all_c)):
                    if np.dot(all_c[k], reference) < 0:
                        all_c[k] = -all_c[k]
                mean_q = all_c.mean(axis=0)
                norm = np.linalg.norm(mean_q)
                parent_quats[idx] = mean_q / norm if norm > 1e-10 else np.array([1, 0, 0, 0])
            else:
                parent_quats[idx] = np.array([1, 0, 0, 0])

        return parent_quats

    def _merge_similar(self):
        if self._config.merge_similar_deg <= 0:
            return
        from pagb_reconstruction.utils.math_ops import misorientation_angle_pair

        sym_quats = self._map._primary_symmetry_quats()
        unique_labels = np.unique(self._parent_labels)
        n = len(unique_labels)

        merge_map = {l: l for l in unique_labels}

        for i in range(n):
            for j in range(i + 1, n):
                li, lj = unique_labels[i], unique_labels[j]
                if li >= len(self._parent_quats) or lj >= len(self._parent_quats):
                    continue
                angle = misorientation_angle_pair(
                    self._parent_quats[li], self._parent_quats[lj], sym_quats
                )
                if angle < self._config.merge_similar_deg:
                    merge_map[lj] = li

        for i in range(len(self._parent_labels)):
            self._parent_labels[i] = merge_map.get(
                self._parent_labels[i], self._parent_labels[i]
            )

    def _merge_inclusions(self):
        if self._config.merge_inclusions_max_size <= 0:
            return
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
                            for j, g in enumerate(self._grains):
                                if g.id == nid and self._parent_labels[j] != label:
                                    neighbor_labels.add(self._parent_labels[j])
                if neighbor_labels:
                    self._parent_labels[indices] = next(iter(neighbor_labels))

    def _compute_variants(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n_pixels = self._map.quaternions.shape[0]
        variant_ids = np.zeros(n_pixels, dtype=np.int32)
        packet_ids = np.zeros(n_pixels, dtype=np.int32)
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
            packet_ids[grain.pixel_indices] = (
                best_variant // 6 if n_variants >= 6 else 0
            )
            bain_ids[grain.pixel_indices] = best_variant % 3

        return variant_ids, packet_ids, bain_ids

    def _compute_fit_angles(self) -> np.ndarray:
        from pagb_reconstruction.utils.math_ops import misorientation_angle_pair

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
                misorientation_angle_pair(c, parent_q, sym_quats)
                for c in candidates
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
