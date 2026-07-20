"""Map rendering guards.

The EBSD map is a pyqtgraph ImageItem. On a display with fractional scaling
(Windows 125/150 %), pyqtgraph's default nearest-neighbour draw at a non-integer
scale drops rows/columns in a regular pattern, producing a uniform cross-hatch /
screen-door moiré over the whole map (reported by a user as "très pixelisé").
Smooth pixmap transform + auto-downsampling removes it. These guard that fix.
"""

from PySide6.QtGui import QPainter


def test_map_view_uses_smooth_pixmap_transform(qtbot):
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    hints = w._graphics_view.renderHints()
    assert hints & QPainter.RenderHint.SmoothPixmapTransform, (
        "map view must enable SmoothPixmapTransform to avoid fractional-scale moiré"
    )


def test_map_image_items_auto_downsample(qtbot):
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    # Base map + split view average on downscale instead of dropping pixels.
    assert w._image_item.autoDownsample is True
    assert w._split_image_item.autoDownsample is True


def test_landscape_map_renders_landscape(qtbot):
    """Issue #9 follow-up: a landscape EBSD map rendered as a narrow portrait
    strip ("déformé pour rentrer dans le rectangle"). pyqtgraph defaults to
    col-major, transposing every numpy (rows, cols) array."""
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    rows, cols = 50, 100  # landscape: wider than tall
    w._image_item.setImage(np.zeros((rows, cols, 3), dtype=np.uint8))
    rect = w._image_item.boundingRect()
    assert (rect.width(), rect.height()) == (cols, rows), (
        f"expected {cols}x{rows} (row-major), got "
        f"{rect.width()}x{rect.height()} — image is transposed"
    )


def test_all_image_items_row_major(qtbot):
    """Every ImageItem must read numpy (rows, cols); the hit-testing and
    boundary/highlight overlays all assume row-major."""
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    for name in ("_image_item", "_boundary_item", "_highlight_item",
                 "_colorbar_item", "_ipf_key_item", "_split_image_item"):
        assert getattr(w, name).axisOrder == "row-major", f"{name} is not row-major"
