import numpy as np


def remap_labels(labels: np.ndarray) -> np.ndarray:
    unique = np.unique(labels)
    remap = {old: new for new, old in enumerate(unique)}
    return np.array([remap[l] for l in labels], dtype=np.int32)


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
