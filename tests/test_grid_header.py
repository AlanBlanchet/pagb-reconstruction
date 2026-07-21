"""Grid geometry must come from the file header, not be inferred from coordinates.

Issue #11: "La cartographie est une 640x480 mais elle n'est pas importée telle
quelle". On a HEXAGONAL scan, odd rows are offset by half a step, so inferring the
step from the smallest coordinate gap yields dx/2 — which doubles the column count
and marks half the grid empty. The header states the true geometry; use it.
"""

import numpy as np
import pytest

from pagb_reconstruction.io.grid_header import read_grid_header


def _write_hex_ang(path, ncols_odd=64, ncols_even=63, nrows=48, dx=0.5):
    dy = dx * np.sqrt(3) / 2
    head = [
        "# TEM_PIXperUM          1.000000",
        "# Phase 1",
        "# MaterialName  Iron bcc",
        "# Symmetry              43",
        "# LatticeConstants      2.870 2.870 2.870  90.000  90.000  90.000",
        "# GRID: HexGrid",
        f"# XSTEP: {dx:.6f}",
        f"# YSTEP: {dy:.6f}",
        f"# NCOLS_ODD: {ncols_odd}",
        f"# NCOLS_EVEN: {ncols_even}",
        f"# NROWS: {nrows}",
        "#",
    ]
    rows = []
    rng = np.random.default_rng(0)
    for r in range(nrows):
        n = ncols_odd if r % 2 == 0 else ncols_even
        xoff = 0.0 if r % 2 == 0 else dx / 2.0
        for c in range(n):
            rows.append(
                f"  {rng.uniform(0, 6.28):.5f}   {rng.uniform(0, 1.5):.5f}   "
                f"{rng.uniform(0, 6.28):.5f}   {xoff + c * dx:.5f}   {r * dy:.5f}  "
                f"1000.0  0.500  1  1  0.500"
            )
    path.write_text("\n".join(head + rows) + "\n")
    return dx, dy


def _write_square_ctf(path, xcells=40, ycells=30, step=0.3):
    head = [
        "Channel Text File",
        "Prj\t",
        "Author\t",
        "JobMode\tGrid",
        f"XCells\t{xcells}",
        f"YCells\t{ycells}",
        f"XStep\t{step:.4f}",
        f"YStep\t{step:.4f}",
        "AcqE1\t0.0000",
        "AcqE2\t0.0000",
        "AcqE3\t0.0000",
        "Euler angles refer to Sample Coordinate system (CS0)!\tMag\t100.0",
        "Phases\t1",
        "2.870;2.870;2.870\t90.000;90.000;90.000\tIron bcc\t11\t225",
        "Phase\tX\tY\tBands\tError\tEuler1\tEuler2\tEuler3\tMAD\tBC\tBS",
    ]
    body = [
        f"1\t{c * step:.4f}\t{r * step:.4f}\t8\t0\t0.1\t0.2\t0.3\t0.5\t100\t100"
        for r in range(ycells)
        for c in range(xcells)
    ]
    path.write_text("\n".join(head + body) + "\n")
    return step


def test_reads_hex_ang_header(tmp_path):
    p = tmp_path / "hex.ang"
    dx, dy = _write_hex_ang(p)
    grid = read_grid_header(p)
    assert grid is not None
    assert grid.hexagonal is True
    assert (grid.n_rows, grid.n_cols) == (48, 64)
    assert grid.dx == pytest.approx(dx)
    assert grid.dy == pytest.approx(dy)


def test_reads_square_ctf_header(tmp_path):
    p = tmp_path / "sq.ctf"
    step = _write_square_ctf(p)
    grid = read_grid_header(p)
    assert grid is not None
    assert grid.hexagonal is False
    assert (grid.n_rows, grid.n_cols) == (30, 40)
    assert grid.dx == pytest.approx(step)
    assert grid.dy == pytest.approx(step)


def test_unknown_format_returns_none(tmp_path):
    p = tmp_path / "x.h5"
    p.write_bytes(b"\x89HDF\r\n\x1a\n")
    assert read_grid_header(p) is None


def test_hex_map_imports_at_true_dimensions(tmp_path):
    """The end-to-end bug: a 48x64 hex scan must not import as 48x127."""
    from pagb_reconstruction.io.base import load_ebsd

    p = tmp_path / "hex.ang"
    dx, dy = _write_hex_ang(p)
    emap = load_ebsd(p)

    assert emap.shape == (48, 64), f"deformed import: {emap.shape}"
    assert emap.step_size == pytest.approx((dy, dx))

    # physical aspect must match the true scan, not a doubled-width one
    rows, cols = emap.shape
    aspect = (cols * dx) / (rows * dy)
    assert aspect == pytest.approx(64 * dx / (48 * dy), rel=1e-6)


def test_square_map_still_imports_correctly(tmp_path):
    """The header path must not disturb square grids, which already worked."""
    from pagb_reconstruction.io.base import load_ebsd

    p = tmp_path / "sq.ctf"
    step = _write_square_ctf(p)
    emap = load_ebsd(p)
    assert emap.shape == (30, 40)
    assert emap.step_size == pytest.approx((step, step))
    assert emap.is_sparse is False
