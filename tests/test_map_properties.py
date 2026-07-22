import numpy as np
from orix.vector import Vector3d

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.utils.colormap import ipf_key_image


def test_ipf_key_image(sample_ebsd):
    img = ipf_key_image(sample_ebsd.primary_symmetry(), Vector3d.zvector())
    assert img.ndim == 3 and img.shape[2] == 4
    assert (img[:, :, :3] < 245).any(), "IPF key triangle should have colored pixels"


def test_all_non_result_properties(sample_ebsd):
    for meta in EBSDMap.registered_map_properties():
        if meta.requires_result:
            continue
        result = sample_ebsd.compute_map_property(meta.name)
        assert isinstance(result, np.ndarray)
        assert result.shape[:2] == sample_ebsd.shape


def test_rgb_maps_are_normalized_to_display_range(sample_ebsd):
    """An RGB display map must be 0-1 floats: the viewer clips anything ≥ 1 to
    white, so a map returning raw values (Euler angles in degrees) renders a
    blank white map. This is the check that would have caught the Euler bug."""
    for meta in EBSDMap.registered_map_properties():
        if meta.requires_result or meta.dtype != "rgb":
            continue
        arr = sample_ebsd.compute_map_property(meta.name)
        finite = arr[np.isfinite(arr)]
        assert finite.size and finite.max() <= 1.0 + 1e-6, (
            f"{meta.name} RGB exceeds 1.0 → the viewer clips it to white"
        )
        assert finite.min() >= -1e-6, f"{meta.name} RGB below 0"
        assert finite.std() > 1e-3, f"{meta.name} is a flat block with no variation"


def test_result_properties(sample_ebsd, variant_graph_result):
    sample_ebsd.set_result(variant_graph_result)
    result_names = [
        "Parent IPF",
        "Parent + Boundaries",
        "Fit Quality",
        "Fit Angle",
        "Packet",
        "Block",
        "Parent Grain ID",
        "Variant ID",
        "Misfit Boundaries",
    ]
    for name in result_names:
        arr = sample_ebsd.compute_map_property(name)
        assert isinstance(arr, np.ndarray)
        assert arr.shape[:2] == sample_ebsd.shape
