"""Read the scan grid geometry straight from the EBSD file header.

orix infers the step size from the smallest gap between unique coordinates. On a
HEXAGONAL scan that is wrong: odd rows sit half a step to the right, so the
inferred dx is half the true one, the column count doubles, and half the grid
becomes empty filler. A 640x480 scan then imports as roughly 480x1279 — the map
the user sees is stretched to twice its width (issue #11).

Both formats state the truth in their header, so read it instead of guessing:
  * EDAX .ang  — ``# GRID:``, ``# XSTEP:``, ``# YSTEP:``, ``# NCOLS_ODD:``,
                 ``# NCOLS_EVEN:``, ``# NROWS:``
  * Oxford .ctf — ``XCells``, ``YCells``, ``XStep``, ``YStep`` (always square)

Returns None for anything we cannot read (e.g. HDF5), leaving the previous
inferred behaviour untouched.
"""

from pathlib import Path

from pagb_reconstruction.core.grid import GridInfo

_MAX_HEADER_LINES = 400


def _read_head(path: Path) -> list[str]:
    try:
        with open(path, encoding="latin-1", errors="replace") as fh:
            return [next(fh, "") for _ in range(_MAX_HEADER_LINES)]
    except OSError:
        return []


def _ang_grid(lines: list[str]) -> GridInfo | None:
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line.startswith("#"):
            continue
        body = line.lstrip("#").strip()
        if ":" not in body:
            continue
        key, _, val = body.partition(":")
        values[key.strip().upper()] = val.strip()

    try:
        n_rows = int(values["NROWS"])
        dx = float(values["XSTEP"])
        dy = float(values["YSTEP"])
    except (KeyError, ValueError):
        return None

    hexagonal = "HEX" in values.get("GRID", "").upper()
    # Odd rows are the long ones on a hex scan; the grid is as wide as they are.
    candidates = []
    for key in ("NCOLS_ODD", "NCOLS_EVEN", "NCOLS"):
        try:
            candidates.append(int(values[key]))
        except (KeyError, ValueError):
            continue
    if not candidates:
        return None

    return GridInfo(n_rows, max(candidates), dx, dy, hexagonal)


def _ctf_grid(lines: list[str]) -> GridInfo | None:
    values: dict[str, str] = {}
    for raw in lines:
        parts = raw.strip().split("\t")
        if len(parts) >= 2:
            values[parts[0].strip().upper()] = parts[1].strip()

    try:
        n_cols = int(values["XCELLS"])
        n_rows = int(values["YCELLS"])
        dx = float(values["XSTEP"])
        dy = float(values["YSTEP"])
    except (KeyError, ValueError):
        return None
    # .ctf is a square grid by construction.
    return GridInfo(n_rows, n_cols, dx, dy, hexagonal=False)


def read_grid_header(path) -> GridInfo | None:
    """Scan geometry from the file header, or None if it cannot be determined."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".ang", ".ctf"}:
        return None

    lines = _read_head(path)
    if not lines:
        return None
    grid = _ang_grid(lines) if suffix == ".ang" else _ctf_grid(lines)
    if grid is None or grid.n_rows <= 0 or grid.n_cols <= 0:
        return None
    if grid.dx <= 0 or grid.dy <= 0:
        return None
    return grid


__all__ = ["GridInfo", "read_grid_header"]
