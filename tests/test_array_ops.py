"""Region-boundary line segments — the crisp parent-grain outlines drawn over
the orientation map (Eloïse's "lines drawn for parents").

A rasterised 1-px boundary mask thins to sub-pixel when a whole 700-px map is in
view, so parent outlines are drawn as vector segments with a screen-space pen
instead. These guard the segment geometry.
"""

import numpy as np

from pagb_reconstruction.utils.array_ops import (
    majority_smooth,
    region_boundary_segments,
)


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
