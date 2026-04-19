import numpy as np

from pagb_reconstruction.core.reconstruction import ReconstructionConfig, ReconstructionEngine


def test_variant_graph_runs(sample_ebsd, variant_graph_result):
    n_pixels = sample_ebsd.shape[0] * sample_ebsd.shape[1]
    assert variant_graph_result.parent_grain_ids.shape == (n_pixels,)
    assert variant_graph_result.parent_orientations.shape == (n_pixels, 4)
    assert variant_graph_result.variant_ids.shape == (n_pixels,)


def test_grain_graph_runs(sample_ebsd):
    config = ReconstructionConfig(algorithm="grain_graph")
    engine = ReconstructionEngine(sample_ebsd, config)
    result = engine.run()
    n_pixels = sample_ebsd.shape[0] * sample_ebsd.shape[1]
    assert result.parent_grain_ids.shape == (n_pixels,)
    assert result.parent_orientations.shape == (n_pixels, 4)


def test_fit_angles_reasonable(variant_graph_result):
    fit = variant_graph_result.fit_angles
    valid = fit[~np.isnan(fit)]
    assert len(valid) > 0
    assert np.mean(valid) < 15.0


def test_parent_ids_valid(variant_graph_result):
    pids = variant_graph_result.parent_grain_ids
    labeled = pids[pids >= 0]
    assert len(labeled) > 0
    assert np.all(labeled >= 0)


def test_variant_ids_valid(variant_graph_result, sample_ebsd):
    from pagb_reconstruction.core.orientation_relationship import OrientationRelationship

    or_obj = OrientationRelationship.from_preset("KS")
    n_variants = or_obj.n_variants
    vids = variant_graph_result.variant_ids
    assert np.all(vids >= 0)
    assert np.all(vids < n_variants)
