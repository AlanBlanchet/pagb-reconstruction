import numpy as np
from scipy import sparse


def remap_labels(labels: np.ndarray) -> np.ndarray:
    """Compact arbitrary labels to a dense ``0..k-1`` range, preserving groups.

    ``np.unique(return_inverse=True)`` already yields each label's rank in
    sorted-unique order — the exact mapping the old dict built, without a Python
    loop over every grain (O(n_grains) on the full-map hot path, issue #16).
    """
    return np.unique(labels, return_inverse=True)[1].ravel().astype(np.int32)


def segment_argmax(
    row_idx: np.ndarray,
    col_idx: np.ndarray,
    weight: np.ndarray,
    n_rows: int,
    n_cols: int,
) -> np.ndarray:
    """For each row, the column with the largest SUMMED weight (grouped argmax).

    Identical to ``np.argmax(dense, axis=1)`` where ``dense`` accumulates
    ``weight`` at each ``(row, col)`` — but never materialises the
    ``n_rows x n_cols`` grid. That dense grid is O(n_rows x n_cols) float64 and
    reached 256 GiB on a full-resolution map (issue #16), even though each row
    carries only a handful of non-zero columns.

    Callers here pass non-negative MCL vote weights, but the equivalence to
    ``np.argmax`` holds for ANY sign: scipy treats unstored entries as 0 and
    breaks ties toward the smallest column index, exactly as ``np.argmax`` does,
    so this is safe as a general primitive. A row with no positive weight
    resolves to column 0, like ``np.argmax`` on an all-zero row.
    """
    vote = sparse.coo_matrix(
        (weight, (row_idx, col_idx)), shape=(n_rows, n_cols)
    ).tocsr()
    # Drop stored exact-zeros so an all-zero row becomes empty; scipy resolves an
    # empty row's argmax to column 0 stably across versions, matching the dense path.
    vote.eliminate_zeros()
    return np.asarray(vote.argmax(axis=1)).ravel()


def boundaries_from_2d(arr: np.ndarray) -> np.ndarray:
    rows, cols = arr.shape
    boundary = np.zeros((rows, cols), dtype=bool)
    boundary[:, :-1] |= arr[:, :-1] != arr[:, 1:]
    boundary[:-1, :] |= arr[:-1, :] != arr[1:, :]
    return boundary


def region_boundary_segments(
    labels: np.ndarray, ignore: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Cell-edge line segments separating adjacent pixels of different label.

    Returns ``(xs, ys)`` where consecutive PAIRS of points are the two ends of
    one segment — the shape ``pyqtgraph.PlotDataItem(connect="pairs")`` draws.
    A pixel ``(r, c)`` spans ``x in [c, c+1]``, ``y in [r, r+1]``, so the edge
    between columns ``c`` and ``c+1`` is the vertical segment ``x = c+1``,
    ``y in [r, r+1]``, and between rows the horizontal segment ``y = r+1``.

    ``ignore`` drops every edge that touches a cell of that label, keeping the
    ragged outline of the unreconstructed (id ``-1``) region off the overlay so
    only real region-vs-region boundaries are traced.

    Vector segments with a screen-space pen stay crisp at any zoom, unlike a
    rasterised 1-px mask that thins to sub-pixel with a whole map in view.
    """
    labels = np.asarray(labels)
    rows, cols = labels.shape

    vdiff = labels[:, :-1] != labels[:, 1:]
    hdiff = labels[:-1, :] != labels[1:, :]
    if ignore is not None:
        vdiff &= (labels[:, :-1] != ignore) & (labels[:, 1:] != ignore)
        hdiff &= (labels[:-1, :] != ignore) & (labels[1:, :] != ignore)

    vr, vc = np.nonzero(vdiff)
    hr, hc = np.nonzero(hdiff)
    nv, nh = vr.size, hr.size

    xs = np.empty(2 * (nv + nh), dtype=np.float64)
    ys = np.empty(2 * (nv + nh), dtype=np.float64)

    # Vertical edges: (c+1, r) -> (c+1, r+1)
    xs[0 : 2 * nv : 2] = xs[1 : 2 * nv : 2] = vc + 1
    ys[0 : 2 * nv : 2] = vr
    ys[1 : 2 * nv : 2] = vr + 1
    # Horizontal edges: (c, r+1) -> (c+1, r+1)
    xs[2 * nv + 0 :: 2] = hc
    xs[2 * nv + 1 :: 2] = hc + 1
    ys[2 * nv + 0 :: 2] = ys[2 * nv + 1 :: 2] = hr + 1
    return xs, ys


def line_intercepts(
    labels: np.ndarray,
    p0: tuple[float, float],
    p1: tuple[float, float],
    ignore: float | None = None,
    step: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """Points where a straight test line ``p0 -> p1`` crosses a boundary between
    two different labels — the crossings counted by the lineal-intercept
    grain-size method (ASTM E112).

    ``p0``/``p1`` are ``(x, y)`` in the pixel coordinates ``region_boundary_segments``
    uses (x = column, y = row; pixel ``(r, c)`` spans ``x in [c, c+1]``). Returns
    ``(xs, ys)`` — the intercept positions in the same coordinates, for drawing
    markers where the line meets each boundary.

    ``ignore`` (the unreconstructed id ``-1``) is not a grain: a transition into
    or out of it is skipped, so a test line only counts real grain-vs-grain
    crossings, never the ragged edge of the reconstructed region.
    """
    labels = np.asarray(labels)
    rows, cols = labels.shape
    (x0, y0), (x1, y1) = p0, p1
    length = float(np.hypot(x1 - x0, y1 - y0))
    if length == 0:
        return np.empty(0), np.empty(0)

    n = max(2, int(np.ceil(length / step)) + 1)
    t = np.linspace(0.0, 1.0, n)
    xs = x0 + t * (x1 - x0)
    ys = y0 + t * (y1 - y0)
    ci = np.clip(np.floor(xs).astype(int), 0, cols - 1)
    ri = np.clip(np.floor(ys).astype(int), 0, rows - 1)
    lab = labels[ri, ci]

    change = lab[1:] != lab[:-1]
    if ignore is not None:
        change &= (lab[1:] != ignore) & (lab[:-1] != ignore)
    idx = np.nonzero(change)[0]
    return (xs[idx] + xs[idx + 1]) / 2, (ys[idx] + ys[idx + 1]) / 2


def majority_smooth(
    labels: np.ndarray,
    iterations: int = 1,
    ignore: int = -1,
    min_agree: int = 5,
) -> np.ndarray:
    """Straighten raster region boundaries by an iterated 8-neighbour majority.

    A pixel flips to the label held by ``>= min_agree`` of its 8 neighbours,
    which erases single-pixel fingers and staircase jaggies while leaving a
    straight boundary — where each side keeps its own majority — as a fixed
    point. This is the raster analogue of MTEX ``smooth(grains)``: it makes the
    parent-grain outline read as the smooth prior-austenite envelope instead of
    tracing every lath seam pixel-for-pixel (Eloïse, issue #14).

    ``ignore`` cells (unreconstructed, id ``-1``) are inviolate — they never
    flip, and no pixel flips *into* them — so boundaries straighten without the
    reconstructed region growing or eroding.
    """
    out = np.asarray(labels).copy()
    if iterations <= 0 or out.ndim != 2:
        return out

    from scipy.stats import mode

    rows, cols = out.shape
    for _ in range(iterations):
        padded = np.pad(out, 1, constant_values=ignore)
        neighbours = np.stack(
            [
                padded[dr : dr + rows, dc : dc + cols]
                for dr in (0, 1, 2)
                for dc in (0, 1, 2)
                if not (dr == 1 and dc == 1)  # the 8 neighbours, not the centre
            ],
            axis=0,
        )
        winner = mode(neighbours, axis=0, keepdims=False)
        flip = (out != ignore) & (winner.mode != ignore) & (winner.count >= min_agree)
        out = np.where(flip, winner.mode, out)
    return out


def align_hemisphere(quats: np.ndarray, ref: np.ndarray) -> np.ndarray:
    aligned = quats.copy()
    for k in range(len(aligned)):
        if np.dot(aligned[k], ref) < 0:
            aligned[k] = -aligned[k]
    return aligned


def grain_index_map(grains) -> dict[int, int]:
    return {g.id: idx for idx, g in enumerate(grains)}
