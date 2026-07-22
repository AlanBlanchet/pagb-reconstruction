"""Region-boundary line segments — the crisp parent-grain outlines drawn over
the orientation map (Eloïse's "lines drawn for parents").

A rasterised 1-px boundary mask thins to sub-pixel when a whole 700-px map is in
view, so parent outlines are drawn as vector segments with a screen-space pen
instead. These guard the segment geometry.
"""

import numpy as np

from pagb_reconstruction.utils.array_ops import region_boundary_segments


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
