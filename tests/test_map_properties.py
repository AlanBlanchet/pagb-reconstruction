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
