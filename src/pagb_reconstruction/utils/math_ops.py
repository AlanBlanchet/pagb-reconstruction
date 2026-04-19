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


def misorientation_angle_pair(
    q1: np.ndarray, q2: np.ndarray, symmetry_quats: np.ndarray
) -> float:
    return float(
        _misori_angle_simple(
            q1.astype(np.float64),
            q2.astype(np.float64),
            symmetry_quats.astype(np.float64),
        )
    )


@njit(cache=True, parallel=True)
def _misori_horizontal(
    quats: np.ndarray, rows: int, cols: int, sym_quats: np.ndarray
) -> np.ndarray:
    result = np.empty(rows * (cols - 1), dtype=np.float64)
    for r in prange(rows):
        for c in range(cols - 1):
            idx1 = r * cols + c
            idx2 = r * cols + c + 1
            result[r * (cols - 1) + c] = _misori_angle_simple(
                quats[idx1], quats[idx2], sym_quats
            )
    return result


@njit(cache=True, parallel=True)
def _misori_vertical(
    quats: np.ndarray, rows: int, cols: int, sym_quats: np.ndarray
) -> np.ndarray:
    result = np.empty((rows - 1) * cols, dtype=np.float64)
    for r in prange(rows - 1):
        for c in range(cols):
            idx1 = r * cols + c
            idx2 = (r + 1) * cols + c
            result[r * cols + c] = _misori_angle_simple(
                quats[idx1], quats[idx2], sym_quats
            )
    return result


def misorientation_angle_neighbors(
    quaternions: np.ndarray, shape: tuple[int, int], symmetry_quats: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = shape
    quats = quaternions.astype(np.float64)
    sym = symmetry_quats.astype(np.float64)
    misori_h = _misori_horizontal(quats, rows, cols, sym)
    misori_v = _misori_vertical(quats, rows, cols, sym)
    return misori_h, misori_v


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
