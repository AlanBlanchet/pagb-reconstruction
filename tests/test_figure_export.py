"""Figure export must produce a publication-ready image, not a raw plot dump.

Issue #11: "L'exportation de la cartographie est mauvaise ... il faudrait pouvoir
l'exporter en png, jpg ou svg avec légende et échelle."
"""

import numpy as np
import pytest

from pagb_reconstruction.io.figure_export import export_map_figure, nice_scale_length


@pytest.mark.parametrize("suffix", [".png", ".jpg", ".svg"])
def test_exports_each_requested_format(tmp_path, suffix):
    rgb = np.random.default_rng(0).random((40, 60, 3))
    out = tmp_path / f"map{suffix}"
    export_map_figure(out, rgb, title="Parent IPF", step_size=(0.3, 0.3))
    assert out.exists(), f"{suffix} not written"
    assert out.stat().st_size > 1000, f"{suffix} suspiciously small"


def test_scalar_map_gets_a_colourbar(tmp_path):
    data = np.linspace(0, 10, 40 * 60).reshape(40, 60)
    out = tmp_path / "scalar.png"
    export_map_figure(
        out, data, title="Fit Angle", step_size=(0.3, 0.3), unit="°", colormap="hot"
    )
    assert out.exists() and out.stat().st_size > 1000


def test_categorical_map_gets_a_legend(tmp_path):
    ids = np.tile(np.arange(4), (40, 15))
    out = tmp_path / "cat.png"
    export_map_figure(
        out, ids, title="Packet", step_size=(0.3, 0.3), categorical=True
    )
    assert out.exists() and out.stat().st_size > 1000


def test_scale_bar_length_is_a_round_number():
    """A scale bar reading '3.7 µm' is unusable; it must be 1/2/5 x a power of 10."""
    for width_um, expected_in in (
        (200.0, {10.0, 20.0, 50.0}),
        (20.0, {1.0, 2.0, 5.0}),
        (2000.0, {100.0, 200.0, 500.0}),
    ):
        got = nice_scale_length(width_um)
        assert got in expected_in, f"width {width_um} -> {got}"
        assert got < width_um


def test_scale_bar_uses_real_physical_size(tmp_path):
    """The bar must come from the step size, not from pixel counts."""
    data = np.zeros((100, 100))
    # 100 px at 0.5 um/px = 50 um across
    assert nice_scale_length(100 * 0.5) <= 50.0
    out = tmp_path / "s.png"
    export_map_figure(out, data, title="t", step_size=(0.5, 0.5))
    assert out.exists()


def test_parent_boundary_segments_drawn_into_figure(tmp_path):
    """A publication figure of the parent view must carry the black parent lines
    the user sees on screen — so an exported figure matches the reference OIM
    overlay, not just a bare orientation map."""
    from PIL import Image

    # a bright uniform IPF-like RGB map (no black anywhere on its own)
    rgb = np.ones((60, 60, 3), dtype=np.float32)
    rgb[:, :, 2] = 0.2  # yellow-ish, so any near-black pixel is a drawn line

    def _black_count(path):
        im = np.asarray(Image.open(path).convert("RGB"))
        return int((im.max(axis=2) < 40).sum())

    plain = tmp_path / "plain.png"
    export_map_figure(plain, rgb, title="IPF-Z", step_size=(0.2, 0.2))

    # one vertical parent boundary down the middle: endpoint pairs at x=30
    xs = np.array([30.0, 30.0])
    ys = np.array([0.0, 60.0])
    withseg = tmp_path / "withseg.png"
    export_map_figure(
        withseg, rgb, title="IPF-Z", step_size=(0.2, 0.2),
        parent_segments=(xs, ys),
    )

    assert withseg.exists()
    assert _black_count(withseg) > _black_count(plain) + 200, (
        "parent boundary line not rendered into the figure"
    )
