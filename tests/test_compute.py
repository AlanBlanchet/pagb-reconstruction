"""Device-aware torch quaternion algebra must match the numpy/orix reference
(within float32 tolerance) — it is the GPU-capable compute path for the
reconstruction hot loops."""

import numpy as np

from pagb_reconstruction.utils.compute import Quaternions
from pagb_reconstruction.utils.math_ops import MisorientationOps, quaternion_multiply


def _rand_quats(n, seed):
    rng = np.random.default_rng(seed)
    q = rng.standard_normal((n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


def test_multiply_matches_scalar():
    a = _rand_quats(5, 1)
    b = _rand_quats(7, 2)
    got = Quaternions.multiply(a[:, None, :], b[None, :, :])
    assert got.shape == (5, 7, 4)
    for i in range(5):
        for j in range(7):
            assert np.allclose(got[i, j], quaternion_multiply(a[i], b[j]), atol=1e-5)


def test_disorientation_matches_misorientation_pair():
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data)
    a = _rand_quats(8, 4)
    b = _rand_quats(8, 5)
    got = Quaternions.disorientation_deg(a, b, sym)
    for i in range(8):
        assert abs(got[i] - MisorientationOps.pair(a[i], b[i], sym)) < 1e-2


def test_pairwise_below_matches_reference():
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data)
    q = _rand_quats(25, 7)
    thr = 40.0
    got = Quaternions.pairwise_below(q, sym, thr)
    assert got.shape == (25, 25)
    for i in range(25):
        for j in range(i + 1, 25):
            assert bool(got[i, j]) == (MisorientationOps.pair(q[i], q[j], sym) < thr)
        assert not got[i, i]


def test_device_is_reported():
    # cuda when a GPU is present, else cpu; overridable via PAGB_DEVICE.
    assert str(Quaternions.device) in {"cuda", "cuda:0", "cpu"}
