import numpy as np

from pagb_reconstruction.core.orientation_relationship import OrientationRelationship


EXPECTED_PRESETS = ["KS", "NW", "GT", "Pitsch", "Bain"]


def test_preset_names():
    names = OrientationRelationship.preset_names()
    for key in EXPECTED_PRESETS:
        assert key in names


def test_from_preset():
    for key in EXPECTED_PRESETS:
        or_obj = OrientationRelationship.from_preset(key)
        assert or_obj.name


def test_variant_quaternions_unit():
    or_obj = OrientationRelationship.from_preset("KS")
    variants = or_obj.variant_quaternions()
    assert len(variants) > 0
    for q in variants:
        assert abs(np.linalg.norm(q) - 1.0) < 1e-6


def test_candidate_parents_shape():
    or_obj = OrientationRelationship.from_preset("KS")
    n_variants = or_obj.n_variants
    child_q = np.array([1.0, 0.0, 0.0, 0.0])
    candidates = or_obj.candidate_parents(child_q)
    assert candidates.shape == (n_variants, 4)
