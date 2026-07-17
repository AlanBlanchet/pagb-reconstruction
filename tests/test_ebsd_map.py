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
