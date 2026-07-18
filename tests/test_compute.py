"""Both compute backends (torch GPU/CPU and the numpy fallback) must match the
numpy/orix reference — they are interchangeable paths for the reconstruction
hot loops. torch is optional (the lean frozen build omits it)."""

import numpy as np
import pytest

from pagb_reconstruction.utils.compute import _HAS_TORCH, _NumpyQuaternions
from pagb_reconstruction.utils.math_ops import MisorientationOps, quaternion_multiply

_BACKENDS = [_NumpyQuaternions]
if _HAS_TORCH:
    from pagb_reconstruction.utils.compute import _TorchQuaternions

    _BACKENDS.append(_TorchQuaternions)


def _rand_quats(n, seed):
    rng = np.random.default_rng(seed)
    q = rng.standard_normal((n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


@pytest.fixture(params=_BACKENDS, ids=lambda b: b.__name__)
def backend(request):
    return request.param


def test_multiply_matches_scalar(backend):
    a, b = _rand_quats(5, 1), _rand_quats(7, 2)
    got = backend.multiply(a[:, None, :], b[None, :, :])
    assert got.shape == (5, 7, 4)
    for i in range(5):
        for j in range(7):
            assert np.allclose(got[i, j], quaternion_multiply(a[i], b[j]), atol=1e-5)


def test_disorientation_matches_pair(backend):
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data)
    a, b = _rand_quats(8, 4), _rand_quats(8, 5)
    got = backend.disorientation_deg(a, b, sym)
    for i in range(8):
        assert abs(got[i] - MisorientationOps.pair(a[i], b[i], sym)) < 1e-2


def test_pairwise_below_matches_reference(backend):
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data)
    q = _rand_quats(25, 7)
    got = backend.pairwise_below(q, sym, 40.0)
    assert got.shape == (25, 25)
    for i in range(25):
        for j in range(i + 1, 25):
            assert bool(got[i, j]) == (MisorientationOps.pair(q[i], q[j], sym) < 40.0)
        assert not got[i, i]


def test_backends_agree(backend):
    """Every backend produces the same fit/variant results (interchangeable)."""
    from orix.quaternion.symmetry import Oh

    sym = np.ascontiguousarray(Oh.data)
    variants = _rand_quats(24, 1)
    parent = _rand_quats(30, 2)
    child = _rand_quats(30, 3)
    ref_fit = _NumpyQuaternions.fit_angles(variants, parent, child, sym)
    ref_var = _NumpyQuaternions.best_variant(variants, parent, child)
    assert np.allclose(backend.fit_angles(variants, parent, child, sym), ref_fit, atol=1e-2)
    assert np.array_equal(backend.best_variant(variants, parent, child), ref_var)
