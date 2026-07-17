"""Batched quaternion ops must match the scalar/orix reference exactly — they
replace per-grain Python/orix loops in the reconstruction hot path."""

import numpy as np

from pagb_reconstruction.utils.math_ops import (
    MisorientationOps,
    quaternion_conjugate_nd,
    quaternion_multiply,
    quaternion_multiply_nd,
    disorientation_deg_nd,
)


def _rand_quats(n, seed):
    rng = np.random.default_rng(seed)
    q = rng.standard_normal((n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


def test_multiply_nd_matches_scalar_over_broadcast():
    a = _rand_quats(5, 1)
    b = _rand_quats(7, 2)
    got = quaternion_multiply_nd(a[:, None, :], b[None, :, :])  # (5,7,4)
    assert got.shape == (5, 7, 4)
    for i in range(5):
        for j in range(7):
            ref = quaternion_multiply(a[i], b[j])
            assert np.allclose(got[i, j], ref, atol=1e-12)


def test_conjugate_nd():
    a = _rand_quats(4, 3)
    c = quaternion_conjugate_nd(a)
    assert np.allclose(c[:, 0], a[:, 0])
    assert np.allclose(c[:, 1:], -a[:, 1:])
    assert not np.shares_memory(c, a)


def test_disorientation_nd_matches_misorientation_pair():
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data, dtype=np.float64)
    a = _rand_quats(6, 4)
    b = _rand_quats(6, 5)
    got = disorientation_deg_nd(a, b, sym)
    for i in range(6):
        ref = MisorientationOps.pair(a[i], b[i], sym)
        assert abs(got[i] - ref) < 1e-6, f"{got[i]} vs {ref}"


def test_pairwise_disor_below_matches_reference():
    from orix.quaternion.symmetry import Oh
    from pagb_reconstruction.utils.math_ops import (
        MisorientationOps, pairwise_disorientation_below,
    )
    sym = np.ascontiguousarray(Oh.data, dtype=np.float64)
    q = _rand_quats(20, 7)
    thr = 40.0
    got = pairwise_disorientation_below(np.ascontiguousarray(q), sym, thr)
    assert got.shape == (20, 20)
    for i in range(20):
        for j in range(i + 1, 20):
            ref = MisorientationOps.pair(q[i], q[j], sym) < thr
            assert bool(got[i, j]) == ref
        assert not got[i, i]  # diagonal + lower stay False
