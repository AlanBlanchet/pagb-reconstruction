"""Quaternion kernels must agree between the CPU and CUDA targets, and with the
numpy reference — they are generated from ONE scalar source, so any divergence
is a compilation/indexing bug, not a maths difference."""

import numpy as np
import pytest

from pagb_reconstruction.utils import quaternion_kernels as qk
from pagb_reconstruction.utils.compute import _NumpyQuaternions


def _rand_quats(n, seed=0):
    rng = np.random.default_rng(seed)
    q = rng.normal(size=(n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


@pytest.fixture(scope="module")
def sym():
    # 24 proper cubic rotations is what the app passes; random unit quats
    # exercise the same code path.
    return _rand_quats(24, seed=7)


def test_multiply_matches_numpy():
    a, b = _rand_quats(500, 1), _rand_quats(500, 2)
    got = qk.kernels().multiply(a, b)
    assert np.allclose(got, _NumpyQuaternions.multiply(a, b), atol=1e-6)


def test_disorientation_matches_numpy(sym):
    a, b = _rand_quats(500, 3), _rand_quats(500, 4)
    got = qk.kernels().disorientation_deg(a, b, sym)
    ref = _NumpyQuaternions.disorientation_deg(a, b, sym)
    assert np.allclose(got, ref, atol=2e-3)


def test_candidate_parents_matches_numpy():
    variants, child = _rand_quats(24, 5), _rand_quats(200, 6)
    got = qk.kernels().candidate_parents(variants, child)
    ref = _NumpyQuaternions.candidate_parents(variants, child)
    assert got.shape == ref.shape
    assert np.allclose(got, ref, atol=1e-6)


def test_best_variant_matches_numpy():
    variants = _rand_quats(24, 8)
    parent, child = _rand_quats(300, 9), _rand_quats(300, 10)
    got = qk.kernels().best_variant(variants, parent, child)
    ref = _NumpyQuaternions.best_variant(variants, parent, child)
    assert np.array_equal(got, ref)


def test_fit_angles_matches_numpy(sym):
    variants = _rand_quats(24, 11)
    parent, child = _rand_quats(300, 12), _rand_quats(300, 13)
    got = qk.kernels().fit_angles(variants, parent, child, sym)
    ref = _NumpyQuaternions.fit_angles(variants, parent, child, sym)
    assert np.allclose(got, ref, atol=2e-3)


def test_pairwise_below_matches_numpy(sym):
    q = _rand_quats(120, 14)
    got = qk.kernels().pairwise_below(q, sym, 35.0)
    ref = _NumpyQuaternions.pairwise_below(q, sym, 35.0)
    assert np.array_equal(got, ref)


def test_variant_edges_matches_numpy(sym):
    variants, child = _rand_quats(6, 15), _rand_quats(40, 16)
    cand = _NumpyQuaternions.candidate_parents(variants, child)
    pairs = np.array([[i, i + 1] for i in range(0, 38, 2)], dtype=np.int64)
    args = (cand, pairs, sym, 8.0, 2.0, 0.1)
    r_g, c_g, w_g = qk.kernels().variant_edges(*args)
    r_r, c_r, w_r = _NumpyQuaternions.variant_edges(*args)
    # same sparse entries, order-independent
    got = sorted(zip(r_g.tolist(), c_g.tolist(), np.round(w_g, 3).tolist()))
    ref = sorted(zip(r_r.tolist(), c_r.tolist(), np.round(w_r, 3).tolist()))
    assert got == ref


def test_refine_or_cost_matches_reference(sym):
    """OR refinement is 84% of a reconstruction. The reference implementation
    allocates two numpy arrays inside its innermost loop (~300k allocations per
    call); the kernel must produce the SAME cost without them."""
    from pagb_reconstruction.utils.math_ops import MisorientationOps

    variants = _rand_quats(24, 21)
    qi, qj = _rand_quats(120, 22), _rand_quats(120, 23)

    got = qk.kernels().refine_or_cost(qi, qj, variants, sym)
    ref = MisorientationOps.refine_or_cost_reference(qi, qj, variants, sym)
    assert abs(got - ref) < 1e-3, f"kernel {got} vs reference {ref}"


def test_refine_or_cost_is_a_mean_over_pairs(sym):
    """Cost is the mean best-angle per pair, so duplicating every pair must not
    change it."""
    import numpy as np

    variants = _rand_quats(24, 24)
    qi, qj = _rand_quats(40, 25), _rand_quats(40, 26)
    single = qk.kernels().refine_or_cost(qi, qj, variants, sym)
    doubled = qk.kernels().refine_or_cost(
        np.vstack([qi, qi]), np.vstack([qj, qj]), variants, sym
    )
    assert abs(single - doubled) < 1e-9
