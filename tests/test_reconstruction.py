import numpy as np
from orix.quaternion import Orientation

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.core.reconstruction import ReconstructionConfig, ReconstructionEngine


def test_recovers_known_parents(synthetic_multi_parent):
    """Ground-truth oracle: three known parents, each region's child grains are
    variants of one parent. A correct reconstruction must recover exactly three
    parents, merge each region into one, and match each known orientation.
    Guards against the symmetry-convention bug (scramble) and over-collapse."""
    emap, region, parents = synthetic_multi_parent
    sym = OrientationRelationship.kurdjumov_sachs().parent_phase.symmetry
    config = ReconstructionConfig(
        algorithm="variant_graph", optimize_or=False, min_grain_size=2
    )
    result = ReconstructionEngine(emap, config).run()

    n_parents = len(np.unique(result.parent_grain_ids[result.parent_grain_ids >= 0]))
    assert n_parents == 3, f"expected 3 parent grains, got {n_parents}"

    recovered = Orientation(result.parent_orientations, symmetry=sym)
    for r in range(3):
        mask = region == r
        ref = Orientation(np.tile(parents[r], (mask.sum(), 1)), symmetry=sym)
        dev = np.rad2deg(recovered[mask].angle_with(ref, degrees=False))
        assert np.median(dev) < 3.0, f"region {r} off by {np.median(dev):.1f} deg"
        labels = result.parent_grain_ids[mask]
        labels = labels[labels >= 0]
        _, counts = np.unique(labels, return_counts=True)
        assert counts.max() / counts.sum() > 0.95, f"region {r} not one parent"


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
