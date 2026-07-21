"""Scan grid geometry.

The authoritative dimensions and step of an EBSD scan. Lives in core because it
is a domain concept; parsing it out of a file header is io's job
(:mod:`pagb_reconstruction.io.grid_header`).
"""

from dataclasses import dataclass


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
