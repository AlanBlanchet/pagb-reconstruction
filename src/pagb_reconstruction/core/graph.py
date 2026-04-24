import numpy as np
from scipy import sparse

from pagb_reconstruction.core.constants import ClusteringDefaults
from pagb_reconstruction.core.grain import Grain
from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.utils.array_ops import grain_index_map, remap_labels
from pagb_reconstruction.utils.math_ops import MathOps, MisorientationOps

_CLUSTERING = ClusteringDefaults()


def build_adjacency_graph(
    grains: list[Grain],
    or_misoris: np.ndarray,
    symmetry_quats: np.ndarray,
    threshold_deg: float = 2.5,
    tolerance_deg: float = 2.5,
) -> sparse.csr_matrix:
    n = len(grains)
    rows, cols, weights = [], [], []
    id_map = grain_index_map(grains)

    for i, grain_i in enumerate(grains):
        for nid in grain_i.neighbor_ids:
            j = id_map.get(nid)
            if j is None or j <= i:
                continue

            angle = MisorientationOps.pair(
                grain_i.mean_quaternion, grains[j].mean_quaternion, symmetry_quats
            )
            prob = _compute_edge_weight(angle, or_misoris, threshold_deg, tolerance_deg)

            if prob > _CLUSTERING.min_edge_weight:
                rows.extend([i, j])
                cols.extend([j, i])
                weights.extend([prob, prob])

    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.csr_matrix(
        (np.array(weights), (np.array(rows), np.array(cols))), shape=(n, n)
    )


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
    return float(MathOps.cumulative_gaussian(min_dev, threshold_deg, tolerance_deg))


def markov_cluster(
    adjacency: sparse.csr_matrix,
    inflation_power: float = _CLUSTERING.inflation_power,
    expansion_power: int = _CLUSTERING.expansion_power,
    max_iterations: int = _CLUSTERING.max_iterations,
    convergence_threshold: float = _CLUSTERING.convergence_threshold,
) -> np.ndarray:
    n = adjacency.shape[0]
    if n == 0:
        return np.array([], dtype=np.int32)

    M = adjacency.astype(np.float64).tocsc()
    M = M + sparse.eye(n, format="csc")

    col_sums = np.array(M.sum(axis=0)).flatten()
    col_sums[col_sums == 0] = 1.0
    M = M.multiply(1.0 / col_sums).tocsc()

    for _ in range(max_iterations):
        M_old = M.copy()

        M_exp = M
        for _p in range(expansion_power - 1):
            M_exp = M_exp @ M
        M = M_exp

        M.data **= inflation_power
        M.data[M.data < _CLUSTERING.prune_threshold] = 0.0
        M.eliminate_zeros()

        col_sums = np.array(M.sum(axis=0)).flatten()
        col_sums[col_sums == 0] = 1.0
        M = M.multiply(1.0 / col_sums).tocsc()

        diff_data = M - M_old
        if diff_data.nnz == 0 or np.abs(diff_data.data).max() < convergence_threshold:
            break

    labels = np.zeros(n, dtype=np.int32)
    diag = np.array(M.diagonal()).flatten()
    attractors = np.where(diag > _CLUSTERING.attractor_threshold)[0]

    if len(attractors) == 0:
        return np.arange(n, dtype=np.int32)

    M_csc = M.tocsc()
    for i in range(n):
        col = M_csc.getcol(i)
        vals = np.array(col[attractors].todense()).flatten()
        labels[i] = attractors[np.argmax(vals)]

    return remap_labels(labels)


def vote_fill(
    grain_labels: np.ndarray,
    grains: list[Grain],
    n_iterations: int = 3,
) -> np.ndarray:
    labels = grain_labels.copy()
    id_map = grain_index_map(grains)

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


def build_variant_graph(
    grains: list[Grain],
    or_obj: OrientationRelationship,
    parent_sym_quats: np.ndarray,
    threshold_deg: float = 2.5,
    tolerance_deg: float = 2.5,
    progress_callback=None,
) -> tuple[sparse.csr_matrix, np.ndarray]:
    n_grains = len(grains)
    n_variants = or_obj.n_variants
    dim = n_grains * n_variants

    all_candidates = np.zeros((n_grains, n_variants, 4))
    for i, grain in enumerate(grains):
        all_candidates[i] = or_obj.candidate_parents(grain.mean_quaternion)

    id_map = grain_index_map(grains)
    edges = []
    for i, grain_i in enumerate(grains):
        for nid in grain_i.neighbor_ids:
            j = id_map.get(nid)
            if j is not None and j > i:
                edges.append((i, j))

    if not edges:
        return sparse.csr_matrix((dim, dim)), all_candidates

    edge_pairs = np.array(edges, dtype=np.int64)

    if progress_callback:
        progress_callback(f"Computing variant edges ({len(edges)} pairs)", 0.35)

    rows, cols, weights = MisorientationOps.build_variant_edges(
        np.ascontiguousarray(all_candidates, dtype=np.float64),
        edge_pairs,
        np.ascontiguousarray(parent_sym_quats, dtype=np.float64),
        n_variants,
        threshold_deg,
        tolerance_deg,
        _CLUSTERING.min_edge_weight,
    )

    mask = rows >= 0
    rows, cols, weights = rows[mask], cols[mask], weights[mask]

    all_rows = np.concatenate([rows, cols])
    all_cols = np.concatenate([cols, rows])
    all_weights = np.concatenate([weights, weights])

    M = sparse.csr_matrix((all_weights, (all_rows, all_cols)), shape=(dim, dim))
    return M, all_candidates


def variant_graph_cluster(
    adj: sparse.csr_matrix,
    all_candidates: np.ndarray,
    n_grains: int,
    n_variants: int,
    inflation: float = _CLUSTERING.variant_inflation,
    max_iter: int = _CLUSTERING.variant_max_iter,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dim = adj.shape[0]
    M = adj.astype(np.float64).tocsc()
    M = M + sparse.eye(dim, format="csc")

    col_sums = np.array(M.sum(axis=0)).flatten()
    col_sums[col_sums == 0] = 1.0
    M = M.multiply(1.0 / col_sums).tocsc()

    for _ in range(max_iter):
        M_old = M.copy()
        M = M @ M
        M.data **= inflation
        M.data[M.data < _CLUSTERING.prune_threshold] = 0.0
        M.eliminate_zeros()
        col_sums = np.array(M.sum(axis=0)).flatten()
        col_sums[col_sums == 0] = 1.0
        M = M.multiply(1.0 / col_sums).tocsc()
        diff = M - M_old
        if diff.nnz == 0 or np.abs(diff.data).max() < _CLUSTERING.convergence_threshold:
            break

    best_variants = np.zeros(n_grains, dtype=np.int32)
    parent_oris = np.zeros((n_grains, 4))

    M_csr = M.tocsr()
    for i in range(n_grains):
        scores = np.zeros(n_variants)
        for v in range(n_variants):
            row = i * n_variants + v
            scores[v] = M_csr[row].sum()
        best_variants[i] = int(np.argmax(scores))
        parent_oris[i] = all_candidates[i, best_variants[i]]

    cluster_labels = np.zeros(n_grains, dtype=np.int32)
    diag = np.array(M.diagonal()).flatten()
    attractors = np.where(diag > _CLUSTERING.attractor_threshold)[0]

    if len(attractors) > 0:
        grain_votes: dict[int, dict[int, float]] = {}
        M_csc = M.tocsc()
        for i in range(dim):
            grain_idx = i // n_variants
            col = M_csc.getcol(i)
            vals = np.array(col[attractors].todense()).flatten()
            best_idx = np.argmax(vals)
            best = attractors[best_idx]
            cluster_id = best // n_variants
            weight = vals[best_idx]
            if grain_idx not in grain_votes:
                grain_votes[grain_idx] = {}
            votes = grain_votes[grain_idx]
            votes[cluster_id] = votes.get(cluster_id, 0.0) + weight
        for grain_idx, votes in grain_votes.items():
            cluster_labels[grain_idx] = max(votes, key=votes.__getitem__)
    else:
        cluster_labels = np.arange(n_grains, dtype=np.int32)

    cluster_labels = remap_labels(cluster_labels)

    return parent_oris, best_variants, cluster_labels
