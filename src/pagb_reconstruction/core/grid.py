"""Scan grid geometry.

The authoritative dimensions and step of an EBSD scan. Lives in core because it
is a domain concept; parsing it out of a file header is io's job
(:mod:`pagb_reconstruction.io.grid_header`).
"""

from dataclasses import dataclass
from typing import NamedTuple


class StepSize(NamedTuple):
    """The scan's physical pixel pitch in µm as ``(dy, dx)``.

    Anisotropic on a hexagonal grid (row pitch ``dy = dx·√3/2 ≈ 0.866·dx``),
    square on a ``SqrGrid``. Unpacks and indexes exactly like the old
    ``(dy, dx)`` tuple, so existing `dy, dx = step_size` sites keep working;
    prefer the named accessors + ``.area`` / ``.display_aspect`` / ``.mpl_aspect``
    so the dx/dy-vs-dy/dx convention is named ONCE rather than re-derived — and
    inverted — at every renderer (Eloïse #15, distances wrong on hex data)."""

    dy: float
    dx: float

    @property
    def area(self) -> float:
        """µm² per pixel — ``dx·dy``, never ``step²`` (wrong on a hex grid)."""
        return self.dx * self.dy

    @property
    def display_aspect(self) -> float:
        """pyqtgraph ``setAspectLocked`` ratio so a micron is a micron in both
        axes: on-screen W/H is ``ratio·(cols/rows)`` and physical W/H is
        ``(cols/rows)·(dx/dy)``, hence ``dx/dy`` (1.0 square, ~1.155 hex)."""
        return (self.dx / self.dy) if self.dy else 1.0

    @property
    def mpl_aspect(self) -> float:
        """matplotlib ``imshow(aspect=…)`` — height:width per pixel = ``dy/dx``,
        the reciprocal of :attr:`display_aspect`."""
        return (self.dy / self.dx) if self.dx else 1.0


@dataclass(frozen=True)
class GridInfo:
    """Authoritative scan geometry as stated by the file itself."""

    n_rows: int
    n_cols: int
    dx: float
    dy: float
    hexagonal: bool

    @property
    def shape(self) -> tuple[int, int]:
        return (self.n_rows, self.n_cols)
