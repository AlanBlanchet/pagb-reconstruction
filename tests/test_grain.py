import numpy as np


def test_detect_grains(sample_with_grains):
    assert sample_with_grains.grains is not None
    assert len(sample_with_grains.grains) > 0


def test_grain_neighbors_symmetric(sample_with_grains):
    grain_map = {g.id: g for g in sample_with_grains.grains}
    for g in sample_with_grains.grains:
        for nid in g.neighbor_ids:
            neighbor = grain_map.get(nid)
            if neighbor is not None:
                assert g.id in neighbor.neighbor_ids


def test_grain_mean_quat_unit(sample_with_grains):
    for g in sample_with_grains.grains:
        assert abs(np.linalg.norm(g.mean_quaternion) - 1.0) < 1e-6


def test_grain_properties(sample_with_grains):
    for g in sample_with_grains.grains[:10]:
        assert g.equivalent_diameter > 0
        assert g.aspect_ratio >= 1.0
