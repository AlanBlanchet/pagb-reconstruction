import numpy as np
from numba import njit, prange


@njit(cache=True)
def quaternion_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = q1[0], q1[1], q1[2], q1[3]
    w2, x2, y2, z2 = q2[0], q2[1], q2[2], q2[3]
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


@njit(cache=True)
def quaternion_conjugate(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]])


@njit(cache=True)
def quaternion_angle(q: np.ndarray) -> float:
    w = min(abs(q[0]), 1.0)
    return 2.0 * np.arccos(w) * 180.0 / np.pi


@njit(cache=True, parallel=True)
def quaternion_multiply_batch(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    n = q1.shape[0]
    result = np.empty((n, 4), dtype=np.float64)
    for i in prange(n):
        result[i] = quaternion_multiply(q1[i], q2[i])
    return result


@njit(cache=True)
def _misori_angle_with_symmetry(
    q1: np.ndarray, q2: np.ndarray, sym_quats: np.ndarray
) -> float:
    q2_inv = quaternion_conjugate(q2)
    mori = quaternion_multiply(q1, q2_inv)

    min_angle = 360.0
    n_sym = sym_quats.shape[0]

    for i in range(n_sym):
        equiv = quaternion_multiply(sym_quats[i], mori)
        for j in range(n_sym):
            final = quaternion_multiply(equiv, quaternion_conjugate(sym_quats[j]))
            if final[0] < 0:
                final = -final
            angle = quaternion_angle(final)
            if angle < min_angle:
                min_angle = angle

    return min_angle


@njit(cache=True)
def _misori_angle_simple(
    q1: np.ndarray, q2: np.ndarray, sym_quats: np.ndarray
) -> float:
    q2_inv = quaternion_conjugate(q2)
    mori = quaternion_multiply(q1, q2_inv)

    min_angle = 360.0
    n_sym = sym_quats.shape[0]

    for i in range(n_sym):
        equiv = quaternion_multiply(sym_quats[i], mori)
        if equiv[0] < 0:
            equiv = -equiv
        angle = quaternion_angle(equiv)
        if angle < min_angle:
            min_angle = angle

    return min_angle


@njit(cache=True)
def cumulative_gaussian(x: float, threshold: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 1.0 if x <= threshold else 0.0
    z = (threshold - x) / tolerance
    return 0.5 * (1.0 + _erf_approx(z / np.sqrt(2.0)))


@njit(cache=True)
def _erf_approx(x: float) -> float:
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (
        ((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
        + 0.254829592
    ) * t * np.exp(-x * x)
    return sign * y


@njit(cache=True, parallel=True)
def _misori_pairs(
    quats: np.ndarray, pairs: np.ndarray, sym_quats: np.ndarray
) -> np.ndarray:
    n = pairs.shape[0]
    result = np.empty(n, dtype=np.float64)
    for i in prange(n):
        result[i] = _misori_angle_simple(
            quats[pairs[i, 0]], quats[pairs[i, 1]], sym_quats
        )
    return result


@njit(cache=True)
def _misori_axis_angle_with_symmetry(
    q1: np.ndarray, q2: np.ndarray, sym_quats: np.ndarray
) -> tuple[float, np.ndarray]:
    q2_inv = quaternion_conjugate(q2)
    mori = quaternion_multiply(q1, q2_inv)

    min_angle = 360.0
    best_axis = np.array([1.0, 0.0, 0.0])
    n_sym = sym_quats.shape[0]

    for i in range(n_sym):
        equiv = quaternion_multiply(sym_quats[i], mori)
        if equiv[0] < 0:
            equiv = -equiv
        angle = quaternion_angle(equiv)
        if angle < min_angle:
            min_angle = angle
            norm = np.sqrt(equiv[1] ** 2 + equiv[2] ** 2 + equiv[3] ** 2)
            if norm > 1e-10:
                best_axis = np.array(
                    [equiv[1] / norm, equiv[2] / norm, equiv[3] / norm]
                )
            else:
                best_axis = np.array([1.0, 0.0, 0.0])

    return min_angle, best_axis


def _rotation_matrix_to_quat(R: np.ndarray) -> np.ndarray:
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 2.0 * np.sqrt(1.0 + trace)
        w, x = 0.25 * s, (R[2, 1] - R[1, 2]) / s
        y, z = (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w, x = (R[2, 1] - R[1, 2]) / s, 0.25 * s
        y, z = (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w, x = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s
        y, z = 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w, x = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s
        y, z = (R[1, 2] + R[2, 1]) / s, 0.25 * s
    q = np.array([w, x, y, z])
    if q[0] < 0:
        q = -q
    return q / np.linalg.norm(q)


@njit(cache=True, parallel=True)
def _refine_or_cost(
    pair_qi: np.ndarray,
    pair_qj: np.ndarray,
    variants: np.ndarray,
    sym_quats: np.ndarray,
) -> float:
    n_pairs = pair_qi.shape[0]
    n_variants = variants.shape[0]
    costs = np.empty(n_pairs, dtype=np.float64)
    for p in prange(n_pairs):
        qi = pair_qi[p]
        qj = pair_qj[p]
        best = 999.0
        for vi in range(n_variants):
            vi_conj = np.array(
                [variants[vi, 0], -variants[vi, 1], -variants[vi, 2], -variants[vi, 3]]
            )
            pi = quaternion_multiply(qi, vi_conj)
            for vj in range(n_variants):
                vj_conj = np.array(
                    [
                        variants[vj, 0],
                        -variants[vj, 1],
                        -variants[vj, 2],
                        -variants[vj, 3],
                    ]
                )
                pj = quaternion_multiply(qj, vj_conj)
                angle = _misori_angle_simple(pi, pj, sym_quats)
                if angle < best:
                    best = angle
        costs[p] = best
    return costs.sum() / n_pairs


@njit(cache=True, parallel=True)
def _build_variant_edges(
    all_candidates: np.ndarray,
    edge_pairs: np.ndarray,
    parent_sym_quats: np.ndarray,
    n_variants: int,
    threshold: float,
    tolerance: float,
    min_weight: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_edges = edge_pairs.shape[0]
    per_edge = n_variants * n_variants
    total_slots = n_edges * per_edge

    rows = np.full(total_slots, -1, dtype=np.int64)
    cols = np.full(total_slots, -1, dtype=np.int64)
    weights = np.zeros(total_slots, dtype=np.float64)

    for e in prange(n_edges):
        i = edge_pairs[e, 0]
        j = edge_pairs[e, 1]
        base = e * per_edge
        count = 0
        for va in range(n_variants):
            for vb in range(n_variants):
                angle = _misori_angle_simple(
                    all_candidates[i, va], all_candidates[j, vb], parent_sym_quats
                )
                w = cumulative_gaussian(angle, threshold, tolerance)
                if w > min_weight:
                    rows[base + count] = i * n_variants + va
                    cols[base + count] = j * n_variants + vb
                    weights[base + count] = w
                    count += 1

    return rows, cols, weights


class QuaternionOps:
    multiply = staticmethod(quaternion_multiply)
    conjugate = staticmethod(quaternion_conjugate)
    angle = staticmethod(quaternion_angle)
    multiply_batch = staticmethod(quaternion_multiply_batch)
    from_rotation_matrix = staticmethod(_rotation_matrix_to_quat)


class MisorientationOps:
    _angle_with_symmetry = staticmethod(_misori_angle_with_symmetry)
    _angle_simple = staticmethod(_misori_angle_simple)
    _axis_angle_with_symmetry = staticmethod(_misori_axis_angle_with_symmetry)
    refine_or_cost = staticmethod(_refine_or_cost)
    build_variant_edges = staticmethod(_build_variant_edges)

    @staticmethod
    def pairs(
        quats: np.ndarray, pair_indices: np.ndarray, symmetry_quats: np.ndarray
    ) -> np.ndarray:
        return _misori_pairs(
            quats.astype(np.float64),
            pair_indices.astype(np.int32),
            symmetry_quats.astype(np.float64),
        )

    @staticmethod
    def pair(q1: np.ndarray, q2: np.ndarray, symmetry_quats: np.ndarray) -> float:
        return float(
            _misori_angle_simple(
                q1.astype(np.float64),
                q2.astype(np.float64),
                symmetry_quats.astype(np.float64),
            )
        )

    @staticmethod
    def axis_angle_pair(
        q1: np.ndarray, q2: np.ndarray, symmetry_quats: np.ndarray
    ) -> tuple[float, np.ndarray]:
        angle, axis = _misori_axis_angle_with_symmetry(
            q1.astype(np.float64),
            q2.astype(np.float64),
            symmetry_quats.astype(np.float64),
        )
        return float(angle), axis


class MathOps:
    _erf_approx = staticmethod(_erf_approx)
    cumulative_gaussian = staticmethod(cumulative_gaussian)
