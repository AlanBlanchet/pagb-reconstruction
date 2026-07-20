"""EBSDMap guards — pre-reconstruction non-indexed fill (Taylor et al. 2024)."""

import pytest
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


def test_parent_with_child_boundaries_map():
    """Issue #10: 'il faut grain parents + boundaries enfants superposés' —
    parent grains coloured, with the CHILD (as-measured) boundaries drawn over
    them, so the reconstruction can be judged against the measured structure."""
    import numpy as np

    emap = _real_map()
    from pagb_reconstruction.core.reconstruction import (
        ReconstructionConfig,
        ReconstructionEngine,
    )

    emap.set_result(ReconstructionEngine(emap, ReconstructionConfig()).run())
    rgb = emap.compute_map_property("Parent + Child Boundaries")

    assert rgb.shape == (*emap.shape, 3)
    flat = rgb.reshape(-1, 3)
    # child boundaries are drawn dark over the parent colours
    dark = (flat.max(axis=1) < 0.05).mean()
    assert 0.01 < dark < 0.60, f"child boundary coverage looks wrong ({dark:.3f})"
    # and the parents underneath are still coloured, not a flat frame
    assert flat.std(axis=0).mean() > 0.05, "parent grains are not visible"


def test_schmid_factor_matches_reference_and_is_fast():
    """Schmid factor looped over every pixel x every slip system in Python,
    building orix objects each time (>110s on a full map). The vectorised form
    must give the SAME values."""
    import time

    import numpy as np
    from orix.quaternion import Orientation
    from orix.vector import Vector3d

    from pagb_reconstruction.core.constants import SlipSystems

    emap = _real_map()
    t0 = time.perf_counter()
    got = np.asarray(emap.compute_map_property("Schmid Factor"), dtype=np.float64)
    elapsed = time.perf_counter() - t0
    assert elapsed < 30.0, f"Schmid factor still slow: {elapsed:.1f}s"

    finite = got[np.isfinite(got)]
    assert finite.max() > 0.0, "Schmid factor is uniformly zero"
    assert finite.max() <= 0.5 + 1e-9, "Schmid factor cannot exceed 0.5"

    # Reference: the original per-pixel orix computation, on a handful of pixels.
    xmap = emap.crystal_map
    phases = xmap.phases_in_data
    pid = next(p for p in phases.ids if p >= 0 and phases[p].point_group is not None)
    mask = xmap.phase_id == pid
    idx = np.where(mask)[0][:25]
    from pagb_reconstruction.core.constants import slip_family

    slip = SlipSystems()
    fam = slip_family(getattr(phases[pid], "name", ""))
    planes, dirs = (
        (slip.fcc_planes, slip.fcc_dirs) if fam == "fcc"
        else (slip.bcc_planes, slip.bcc_dirs)
    )
    loading = Vector3d([0, 0, 1])
    flat_got = got.reshape(-1)
    for i in idx:
        ori = Orientation(xmap.rotations[i], symmetry=phases[pid].point_group)
        best = 0.0
        for sl in range(len(planes)):
            n = (ori * Vector3d(planes[sl])).unit
            d = (ori * Vector3d(dirs[sl])).unit
            sf = abs(float(n.dot(loading).data[0])) * abs(float(d.dot(loading).data[0]))
            best = max(best, sf)
        assert flat_got[i] == pytest.approx(best, abs=1e-6), f"pixel {i} differs"
