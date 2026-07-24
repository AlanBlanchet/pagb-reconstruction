"""Region-boundary line segments — the crisp parent-grain outlines drawn over
the orientation map (Eloïse's "lines drawn for parents").

A rasterised 1-px boundary mask thins to sub-pixel when a whole 700-px map is in
view, so parent outlines are drawn as vector segments with a screen-space pen
instead. These guard the segment geometry.
"""

import numpy as np
import pytest

from pagb_reconstruction.utils.array_ops import (
    line_intercepts,
    majority_smooth,
    region_boundary_segments,
    remap_labels,
    segment_argmax,
)


def _dense_segment_argmax(row, col, w, n_rows, n_cols):
    """The pre-issue-#16 dense reference: accumulate then argmax per row."""
    dense = np.zeros((n_rows, n_cols))
    np.add.at(dense, (np.asarray(row), np.asarray(col)), np.asarray(w, dtype=float))
    return np.argmax(dense, axis=1)


@pytest.mark.parametrize(
    "row, col, w, n_rows, n_cols",
    [
        # distinct entries, one per row
        ([0, 1, 2], [2, 0, 1], [1.0, 1.0, 1.0], 3, 3),
        # DUPLICATE (row, col) pairs must SUM (col 0 of row 0 wins: 0.6 > 0.5)
        ([0, 0, 0], [0, 0, 1], [0.3, 0.3, 0.5], 1, 2),
        # a TIE inside a row resolves to the smallest column index
        ([0, 0], [2, 0], [1.0, 1.0], 1, 3),
        # an ALL-ZERO row (no positive weight) resolves to column 0
        ([0, 1], [1, 2], [0.0, 0.9], 2, 3),
        # more rows than entries: untouched rows argmax to 0
        ([1], [3], [0.7], 4, 4),
        # MIXED SIGN: not a real regime here, but the primitive must stay
        # equivalent to dense for any sign (scipy treats unstored cells as 0).
        ([0, 0, 1, 1], [0, 2, 1, 2], [-0.5, -0.1, -0.9, -0.2], 2, 3),
    ],
)
def test_segment_argmax_matches_dense(row, col, w, n_rows, n_cols):
    got = segment_argmax(np.array(row), np.array(col), np.array(w), n_rows, n_cols)
    want = _dense_segment_argmax(row, col, w, n_rows, n_cols)
    assert got.shape == (n_rows,)
    np.testing.assert_array_equal(got, want)


def test_segment_argmax_random_parity():
    rng = np.random.default_rng(0)
    n_rows, n_cols = 200, 60
    k = 2000  # many duplicate (row, col) pairs -> exercises summation
    row = rng.integers(0, n_rows, k)
    col = rng.integers(0, n_cols, k)
    w = rng.random(k)
    got = segment_argmax(row, col, w, n_rows, n_cols)
    want = _dense_segment_argmax(row, col, w, n_rows, n_cols)
    np.testing.assert_array_equal(got, want)


def test_segment_argmax_scales_without_dense():
    """The issue-#16 regime: ~200k rows/cols. A dense grid would be 320 GiB;
    the sparse grouped argmax must run in a blink."""
    n = 200_000
    rows = np.repeat(np.arange(n), 2)     # [0,0,1,1,2,2,...]
    cols = np.empty(2 * n, dtype=np.int64)
    cols[0::2] = np.arange(n)             # each row's diagonal
    cols[1::2] = (np.arange(n) + 1) % n   # and a weaker off-diagonal
    w = np.empty(2 * n)
    w[0::2] = 1.0
    w[1::2] = 0.5
    got = segment_argmax(rows, cols, w, n, n)
    assert got.shape == (n,)
    # the diagonal entry (weight 1.0) beats the off-diagonal (0.5) in every row
    np.testing.assert_array_equal(got, np.arange(n))


@pytest.mark.parametrize(
    "labels",
    [
        [5, 5, 2, 9, 2],       # unsorted, gapped
        [-1, 0, 3, -1, 3],     # negatives (the unreconstructed sentinel)
        [7],                   # single
        [],                    # empty
        [0, 1, 2, 3],          # already compact
    ],
)
def test_remap_labels_matches_dict(labels):
    labels = np.array(labels, dtype=np.int64)
    unique = np.unique(labels)
    old = np.array([{o: n for n, o in enumerate(unique)}[l] for l in labels], dtype=np.int32)
    got = remap_labels(labels)
    assert got.dtype == np.int32
    np.testing.assert_array_equal(got, old)


def _segset(xs, ys):
    assert len(xs) == len(ys), "endpoint arrays must be the same length"
    assert len(xs) % 2 == 0, "segments come in endpoint PAIRS for connect='pairs'"
    return {
        (
            round(float(xs[i]), 3),
            round(float(ys[i]), 3),
            round(float(xs[i + 1]), 3),
            round(float(ys[i + 1]), 3),
        )
        for i in range(0, len(xs), 2)
    }


def test_segments_trace_edges_between_differing_labels():
    # pixel (r, c) spans x in [c, c+1], y in [r, r+1]
    labels = np.array([[0, 0, 1],
                       [0, 1, 1]], dtype=float)
    segs = _segset(*region_boundary_segments(labels))

    # vertical edge between col1|col2 on row0 (0 vs 1): x=2, y 0->1
    assert (2.0, 0.0, 2.0, 1.0) in segs
    # vertical edge between col0|col1 on row1 (0 vs 1): x=1, y 1->2
    assert (1.0, 1.0, 1.0, 2.0) in segs
    # horizontal edge between row0|row1 on col1 (0 vs 1): y=1, x 1->2
    assert (1.0, 1.0, 2.0, 1.0) in segs
    # a uniform interior edge (col0|col1 row0, both 0) draws nothing
    assert (1.0, 0.0, 1.0, 1.0) not in segs


def test_uniform_field_has_no_segments():
    xs, ys = region_boundary_segments(np.zeros((5, 5), dtype=float))
    assert xs.size == 0 and ys.size == 0


def test_ignore_value_suppresses_edges_touching_it():
    labels = np.array([[0, -1],
                       [0, 0]], dtype=float)
    # both differing edges touch the -1 cell, so ignoring it leaves nothing —
    # this is how the ragged unreconstructed border is kept off the overlay
    xs, _ = region_boundary_segments(labels, ignore=-1)
    assert xs.size == 0
    # without ignore, the two edges around the -1 cell appear (2 segs -> 4 points)
    xs_all, _ = region_boundary_segments(labels)
    assert xs_all.size == 4


# ── majority_smooth: straighten the jagged parent boundaries (MTEX `smooth`) ──
# Eloïse #14: "parent boundaries should be STRAIGHT lines; here they trace the
# curved LATH boundaries." A raster label map draws a boundary at every pixel
# step, so single-pixel fingers/notches read as wiggly lath-following lines.


def test_majority_smooth_is_a_noop_at_zero_iterations():
    a = np.array([[0, 1], [1, 0]], dtype=np.int32)
    assert np.array_equal(majority_smooth(a, iterations=0), a)


def test_majority_smooth_heals_a_single_pixel_notch():
    a = np.ones((5, 5), dtype=np.int32)
    a[2, 2] = 0  # a lone 0 poking into a field of 1s
    out = majority_smooth(a, iterations=1)
    assert out[2, 2] == 1
    assert (out == 0).sum() == 0


def test_majority_smooth_keeps_a_straight_boundary_fixed():
    # A straight boundary is already minimal — smoothing must not walk it.
    a = np.zeros((6, 6), dtype=np.int32)
    a[:, 3:] = 1
    assert np.array_equal(majority_smooth(a, iterations=3), a)


def test_majority_smooth_reduces_a_ragged_boundary():
    a = np.zeros((7, 9), dtype=np.int32)
    a[:, 5:] = 1
    a[3, 4] = 1  # a 1-finger poking into the 0 field
    a[1, 5] = 0  # a 0-notch poking into the 1 field
    before = region_boundary_segments(a)[0].size
    out = majority_smooth(a, iterations=1)
    after = region_boundary_segments(out)[0].size
    assert after < before, "smoothing shortens the jagged boundary"
    assert out[3, 4] == 0 and out[1, 5] == 1, "both defects heal to the flat edge"


def test_majority_smooth_never_erodes_into_unreconstructed():
    # -1 (unreconstructed) is inviolate: parents neither fill it nor bleed away.
    a = np.ones((5, 5), dtype=np.int32)
    a[:, 0] = -1
    out = majority_smooth(a, iterations=3, ignore=-1)
    assert (out == -1).sum() == 5
    assert (out[:, 1:] == 1).all()


# ── line-intercept grain-size measurement (ASTM E112), Eloïse issue #15 ──


def test_line_intercepts_counts_grain_boundary_crossings():
    # three vertical bands: cols 0-3 → 0, 4-6 → 1, 7-9 → 2
    labels = np.zeros((10, 10), dtype=int)
    labels[:, 4:7] = 1
    labels[:, 7:] = 2
    # a horizontal test line down the middle crosses two boundaries (~x=4, ~x=7)
    ix, iy = line_intercepts(labels, (0.5, 5.0), (9.5, 5.0))
    assert len(ix) == 2
    assert abs(ix[0] - 4.0) < 1.0 and abs(ix[1] - 7.0) < 1.0
    assert np.allclose(iy, 5.0)


def test_line_intercepts_skips_unreconstructed_transitions():
    # right half unreconstructed (-1): the 0 → -1 edge is NOT a grain boundary
    labels = np.zeros((10, 10), dtype=int)
    labels[:, 5:] = -1
    assert len(line_intercepts(labels, (0.5, 5.0), (9.5, 5.0), ignore=-1)[0]) == 0
    # without ignore, the label change IS counted
    assert len(line_intercepts(labels, (0.5, 5.0), (9.5, 5.0))[0]) == 1


def test_line_intercepts_degenerate_line_is_empty():
    labels = np.zeros((5, 5), dtype=int)
    ix, iy = line_intercepts(labels, (2.0, 2.0), (2.0, 2.0))
    assert len(ix) == 0 and len(iy) == 0
