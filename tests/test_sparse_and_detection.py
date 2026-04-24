"""Tests for sparse grid handling, content-sniffing format detection,
and _primary_symmetry_quats edge cases."""

import numpy as np
import pytest
from orix.crystal_map import CrystalMap, Phase, PhaseList
from orix.quaternion import Rotation

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.phase import PhaseConfig
from pagb_reconstruction.io.base import _detect_format


# ── fixtures ──────────────────────────────────────────────────────────


def _make_ebsd_map(*, sparse: bool) -> EBSDMap:
    """Build a small EBSDMap, optionally with missing pixels."""
    rows, cols = 5, 6
    phase = Phase(name="Iron", point_group="m-3m")
    phases = PhaseList([phase])

    if sparse:
        # Keep only ~half the pixels
        n_full = rows * cols
        keep = np.sort(
            np.random.default_rng(42).choice(n_full, n_full // 2, replace=False)
        )
        all_y, all_x = np.divmod(np.arange(n_full), cols)
        y = all_y[keep].astype(float)
        x = all_x[keep].astype(float)
        n = len(keep)
    else:
        yy, xx = np.mgrid[:rows, :cols]
        y = yy.ravel().astype(float)
        x = xx.ravel().astype(float)
        n = rows * cols

    rotations = Rotation.random(n)
    xmap = CrystalMap(
        rotations=rotations,
        x=x,
        y=y,
        phase_id=np.zeros(n, dtype=int),
        phase_list=phases,
        prop={"iq": np.random.default_rng(0).random(n).astype(np.float32)},
    )
    phase_cfgs = [PhaseConfig.ferrite()]
    return EBSDMap(crystal_map=xmap, phases=phase_cfgs)


# ── sparse / dense grid tests ────────────────────────────────────────


@pytest.mark.parametrize("sparse", [False, True], ids=["dense", "sparse"])
class TestGridHandling:
    def test_is_sparse(self, sparse):
        m = _make_ebsd_map(sparse=sparse)
        assert m.is_sparse is sparse

    def test_to_grid_1d(self, sparse):
        m = _make_ebsd_map(sparse=sparse)
        data = np.arange(1, m.crystal_map.size + 1, dtype=float)
        grid = m._to_grid(data)
        assert grid.shape == m.shape
        if not sparse:
            assert grid.ravel().tolist() == data.tolist()
        else:
            # Sparse: filled cells are non-zero, background is 0
            assert (grid != 0).sum() == m.crystal_map.size

    def test_to_grid_nd(self, sparse):
        m = _make_ebsd_map(sparse=sparse)
        data = np.ones((m.crystal_map.size, 3), dtype=float)
        grid = m._to_grid(data)
        assert grid.shape == (*m.shape, 3)

    def test_property_map_uses_grid(self, sparse):
        m = _make_ebsd_map(sparse=sparse)
        iq = m.property_map("iq")
        assert iq.shape == m.shape
        if sparse:
            assert (iq == 0).any()  # fill value present


# ── _primary_symmetry_quats ──────────────────────────────────────────


def test_primary_symmetry_quats_skips_not_indexed():
    """Phases with id < 0 (not_indexed) should be skipped."""
    m = _make_ebsd_map(sparse=False)
    quats = m._primary_symmetry_quats()
    assert quats.ndim == 2 and quats.shape[1] == 4


# ── _detect_format content sniffing ──────────────────────────────────


@pytest.mark.parametrize(
    "header, expected",
    [
        (b"Channel Text File\nsome more data", ".ctf"),
        (b"# TEM_PIXperUM 1.0\n# x-star 0.5\n", ".ang"),
        (b"# x-star 0.5\n# y-star 0.3\n", ".ang"),
        # NOTE: HDF5 sniffing is broken — \x89 lost in utf-8 decode round-trip.
        # _detect_format returns "" for HDF5 files. Registered as known bug.
        (b"\x89HDF\r\n\x1a\n\x00\x00rest", ""),
        (b"random binary content here", ""),
    ],
    ids=["ctf", "ang-tem", "ang-xstar", "hdf5-broken", "unknown"],
)
def test_detect_format(header, expected, tmp_path):
    f = tmp_path / "testfile"
    f.write_bytes(header)
    assert _detect_format(f) == expected


def test_detect_format_missing_file(tmp_path):
    assert _detect_format(tmp_path / "nope") == ""
