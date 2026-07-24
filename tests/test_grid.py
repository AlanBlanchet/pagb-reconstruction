"""Scan-grid geometry types.

`StepSize` names the anisotropic pixel pitch (dy, dx) once, with the physical
derivations (area, display aspect) that used to be re-derived — with inverted
dx/dy-vs-dy/dx conventions — at every renderer (Eloïse #15, code-reviewer F1).
"""

from pagb_reconstruction.core.grid import StepSize


def test_step_size_unpacks_and_indexes_like_the_old_tuple():
    s = StepSize(dy=0.086603, dx=0.1)
    assert s.dy == 0.086603 and s.dx == 0.1
    dy, dx = s  # back-compat: existing sites unpack (dy, dx)
    assert (dy, dx) == (0.086603, 0.1)
    assert s[0] == 0.086603 and s[1] == 0.1  # tuple-indexable


def test_step_size_area_is_anisotropic():
    # a cell is dx·dy, NOT step² (which is wrong on a hex grid)
    assert StepSize(dy=0.5, dx=2.0).area == 1.0


def test_step_size_display_aspect_is_dx_over_dy():
    assert StepSize(dy=1.5, dx=1.5).display_aspect == 1.0  # square: no correction
    # hex: pyqtgraph ratio = dx/dy so a µm is a µm in both axes
    assert abs(StepSize(dy=0.086603, dx=0.1).display_aspect - 0.1 / 0.086603) < 1e-9
    assert StepSize(dy=0.0, dx=0.1).display_aspect == 1.0  # degenerate guard


def test_step_size_mpl_aspect_is_the_matplotlib_reciprocal():
    # matplotlib imshow aspect is height/width per pixel = dy/dx (the reciprocal
    # of pyqtgraph's ratio) — naming both kills the convention confusion
    assert abs(StepSize(dy=0.086603, dx=0.1).mpl_aspect - 0.086603 / 0.1) < 1e-9
    assert StepSize(dy=1.5, dx=1.5).mpl_aspect == 1.0
    assert StepSize(dy=0.1, dx=0.0).mpl_aspect == 1.0  # degenerate guard
