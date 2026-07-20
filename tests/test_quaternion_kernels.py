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
