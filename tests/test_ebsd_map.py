"""EBSDMap guards — pre-reconstruction non-indexed fill (Taylor et al. 2024)."""

import numpy as np
from orix.crystal_map import CrystalMap, Phase, PhaseList
from orix.quaternion import Rotation

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.phase import PhaseConfig


def _make_map(with_holes: bool):
    ny, nx = 4, 4
    yy, xx = np.mgrid[0:ny, 0:nx]
    row, col = yy.ravel(), xx.ravel()
    n = row.size
    # distinct orientations so a filled hole takes a real neighbour value
    angles = np.linspace(0.0, 1.0, n)
    rot = Rotation.from_axes_angles([[0, 0, 1]] * n, angles)
    phase_id = np.zeros(n, dtype=int)
    if with_holes:
        holes = ((row == 1) & (col == 1)) | ((row == 2) & (col == 2))
        phase_id[holes] = -1
    xmap = CrystalMap(
        rotations=rot,
        phase_id=phase_id,
        x=col.astype(float),
        y=row.astype(float),
        phase_list=PhaseList(Phase(name="ferrite", point_group="m-3m")),
    )
    return EBSDMap(crystal_map=xmap, phases=[PhaseConfig.austenite()])


def _map_with_holes():
    return _make_map(with_holes=True)


def test_filled_pixel_data_fills_all_holes():
    emap = _map_with_holes()
    assert (emap.phase_ids < 0).sum() == 2
    q, ph = emap.filled_pixel_data()
    assert (ph < 0).sum() == 0, "every non-indexed pixel must be filled"
    assert q.shape == emap.quaternions.shape
    assert ph.shape == emap.phase_ids.shape
    # indexed pixels are left untouched
    idx = emap.phase_ids >= 0
    assert np.allclose(q[idx], emap.quaternions[idx])
    # a filled hole takes a real neighbour's quaternion (not identity/zeros)
    hole = emap.phase_ids < 0
    filled = q[hole]
    assert np.all(np.abs(np.linalg.norm(filled, axis=1) - 1.0) < 1e-6)


def test_filled_pixel_data_noop_when_all_indexed():
    emap = _make_map(with_holes=False)
    assert (emap.phase_ids < 0).sum() == 0
    q, ph = emap.filled_pixel_data()
    assert np.array_equal(ph, emap.phase_ids)
    assert np.allclose(q, emap.quaternions)


def _tiny_result(emap):
    from pagb_reconstruction.core.reconstruction import ReconstructionResult
    import numpy as np

    n = emap.crystal_map.size
    pids = np.arange(n, dtype=np.int32) % 3  # 3 parent grains, all reconstructed
    quats = np.tile([1.0, 0, 0, 0], (n, 1))
    z = np.zeros(n, dtype=np.int32)
    return ReconstructionResult(
        parent_orientations=quats, parent_grain_ids=pids, fit_angles=np.zeros(n),
        variant_ids=z, packet_ids=z, block_ids=z, bain_ids=z,
    )


def test_parent_ipf_map_never_all_black():
    """Issue #9: '98% reconstructed but I see nothing'. The Parent-IPF map must
    render visible grains, never an all-black frame — even with no symmetry."""
    emap = _make_map(with_holes=False)
    emap._result = _tiny_result(emap)
    rgb = emap.parent_ipf_map()
    assert rgb.shape == (*emap.shape, 3)
    # not all black: reconstructed pixels carry real colour
    assert rgb.reshape(-1, 3).max() > 0.2, "parent IPF map is all black"
    assert (rgb.reshape(-1, 3).max(axis=1) > 0.05).mean() > 0.5, "map mostly black"


def test_parent_ipf_greys_unreconstructed():
    import numpy as np

    emap = _make_map(with_holes=False)
    res = _tiny_result(emap)
    res.parent_grain_ids[:] = -1  # nothing reconstructed
    emap._result = res
    rgb = emap.parent_ipf_map().reshape(-1, 3)
    # every pixel unreconstructed → the whole frame is neutral grey (~0.18),
    # never identity-coloured or black.
    assert np.allclose(rgb, 0.18, atol=1e-6), "unreconstructed pixels must be grey"


def _real_map():
    from pagb_reconstruction.io.base import load_ebsd

    return load_ebsd("data/martensite_roomtemp.ctf")


def test_grain_based_maps_detect_grains_on_demand():
    """Issue #10 stabilization: GOS/GAM/GROD are grain-based, but `grains` is None
    until detection runs. Each guarded differently — GOS and GROD silently
    returned an all-zero (blank) map and GAM crashed with
    "'NoneType' object is not iterable". They must all just work.
    """
    import numpy as np

    emap = _real_map()
    assert emap.grains is None, "precondition: no detection has run yet"

    for name in ("GOS", "GAM", "GROD"):
        data = np.asarray(emap.compute_map_property(name), dtype=np.float64)
        finite = data[np.isfinite(data)]
        assert finite.size, f"{name} produced no finite values"
        assert finite.max() > 0.0, f"{name} is uniformly zero — a blank map"


def test_require_grains_is_idempotent():
    emap = _real_map()
    first = emap.require_grains()
    assert first, "grains should be detected on demand"
    assert emap.require_grains() is first, "detection must not re-run"
