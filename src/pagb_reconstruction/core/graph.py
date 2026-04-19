import numpy as np
from scipy import sparse

from pagb_reconstruction.core.grain import Grain
from pagb_reconstruction.utils.math_ops import cumulative_gaussian


def build_adjacency_graph(
    grains: list[Grain],
    or_misoris: np.ndarray,
    symmetry_quats: np.ndarray,
    threshold_deg: float = 2.5,
    tolerance_deg: float = 2.5,
) -> sparse.csr_matrix:
    from pagb_reconstruction.utils.math_ops import misorientation_angle_pair

    n = len(grains)
    rows, cols, weights = [], [], []
    id_map = _grain_id_to_index(grains)

    for i, grain_i in enumerate(grains):
        for nid in grain_i.neighbor_ids:
            j = id_map.get(nid)
            if j is None or j <= i:
                continue

            angle = misorientation_angle_pair(
                grain_i.mean_quaternion, grains[j].mean_quaternion, symmetry_quats
            )
            prob = _compute_edge_weight(angle, or_misoris, threshold_deg, tolerance_deg)

            if prob > 0.01:
                rows.extend([i, j])
                cols.extend([j, i])
                weights.extend([prob, prob])

    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.csr_matrix(
        (np.array(weights), (np.array(rows), np.array(cols))), shape=(n, n)
    )


def _grain_id_to_index(grains: list[Grain]) -> dict[int, int]:
    return {g.id: idx for idx, g in enumerate(grains)}


def _grain_index(grains: list[Grain], grain_id: int) -> int | None:
    for idx, g in enumerate(grains):
        if g.id == grain_id:
            return idx
    return None


def _compute_edge_weight(
    measured_angle: float,
    theoretical_angles: np.ndarray,
    threshold_deg: float,
    tolerance_deg: float,
) -> float:
    if len(theoretical_angles) == 0:
        return 0.0
    deviations = np.abs(theoretical_angles - measured_angle)
    min_dev = np.min(deviations)
    return float(cumulative_gaussian(min_dev, threshold_deg, tolerance_deg))


def markov_cluster(
    adjacency: sparse.csr_matrix,
    inflation_power: float = 1.6,
    expansion_power: int = 2,
    max_iterations: int = 100,
    convergence_threshold: float = 1e-5,
) -> np.ndarray:
    n = adjacency.shape[0]
    if n == 0:
        return np.array([], dtype=np.int32)

    M = adjacency.toarray().astype(np.float64)
    np.fill_diagonal(M, 1.0)

    col_sums = M.sum(axis=0)
    col_sums[col_sums == 0] = 1.0
    M /= col_sums[np.newaxis, :]

    for _ in range(max_iterations):
        M_old = M.copy()

        M = np.linalg.matrix_power(M, expansion_power)

        M = np.power(M, inflation_power)

        col_sums = M.sum(axis=0)
        col_sums[col_sums == 0] = 1.0
        M /= col_sums[np.newaxis, :]

        if np.abs(M - M_old).max() < convergence_threshold:
            break

    labels = np.zeros(n, dtype=np.int32)
    attractors = np.where(np.diag(M) > 0.01)[0]

    if len(attractors) == 0:
        return np.arange(n, dtype=np.int32)

    for i in range(n):
        best_attractor = attractors[np.argmax(M[attractors, i])]
        labels[i] = best_attractor

    unique_labels = np.unique(labels)
    label_remap = {old: new for new, old in enumerate(unique_labels)}
    return np.array([label_remap[l] for l in labels], dtype=np.int32)


def vote_fill(
    grain_labels: np.ndarray,
    grains: list[Grain],
    n_iterations: int = 3,
) -> np.ndarray:
    labels = grain_labels.copy()
    id_map = _grain_id_to_index(grains)

    for _ in range(n_iterations):
        changed = False
        for i, grain in enumerate(grains):
            if labels[i] >= 0:
                continue
            neighbor_indices = [id_map.get(nid) for nid in grain.neighbor_ids]
            neighbor_indices = [
                idx for idx in neighbor_indices if idx is not None and labels[idx] >= 0
            ]
            if not neighbor_indices:
                continue
            neighbor_labels = [labels[idx] for idx in neighbor_indices]
            counts = {}
            for nl in neighbor_labels:
                counts[nl] = counts.get(nl, 0) + 1
            labels[i] = max(counts, key=counts.get)
            changed = True
        if not changed:
            break

    return labels
