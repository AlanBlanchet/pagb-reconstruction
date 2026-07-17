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
