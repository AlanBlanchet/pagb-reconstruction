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


def test_switching_mode_keeps_running_worker_alive(qtbot):
    """A superseded compute must stay referenced until its thread stops.

    Dropping a running QThread makes Qt abort the process ("QThread: Destroyed
    while thread is still running") — a crash reachable by changing display mode
    while one is still computing.
    """
    import time

    from pagb_reconstruction.ui.widgets.compute_worker import ComputeWorker
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    slow = ComputeWorker(lambda: time.sleep(0.4))
    w._active_worker = slow
    slow.start()
    qtbot.waitUntil(slow.isRunning, timeout=2000)

    w._retire_active_worker()
    assert w._active_worker is None
    assert slow in w._retired_workers, "running worker was dropped — Qt would abort"

    qtbot.waitUntil(lambda: not slow.isRunning(), timeout=5000)
    qtbot.waitUntil(lambda: slow not in w._retired_workers, timeout=5000)


def test_discrete_ids_cycle_instead_of_clamping(qtbot):
    """Issue #10: 'IPF parents ne marche pas à l'affichage'.

    Discrete maps were drawn with levels=(0, 255) against a 256-entry LUT, so on
    a map with thousands of ids (4155 parent grains) every id past 255 clamped to
    ONE colour. Ids are assigned in raster order, so only the top rows stayed
    coloured and the rest went flat — a smooth ramp under a grey colormap.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    idx = MapViewer._discrete_indices(np.array([[300.0, 700.0, 4000.0]]), 256)
    assert len(set(idx.ravel().tolist())) == 3, "high ids collapsed to one colour"

    # negative / non-finite means "no id" and must take the reserved slot 0
    special = MapViewer._discrete_indices(np.array([[-1.0, np.nan]]), 256)
    assert special.ravel().tolist() == [0.0, 0.0]


def test_categorical_lut_reserves_slot_zero(qtbot):
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    lut = MapViewer._categorical_lut()
    assert lut.shape == (256, 3)
    # slot 0 is the neutral "no id" colour, distinct from the cycling palette
    assert not (lut[0] == lut[1]).all()


def test_failed_compute_clears_stale_image(qtbot):
    """A failed map computation must not leave the PREVIOUS map on screen.

    Otherwise the user selects e.g. GOS, the compute fails, and they keep looking
    at KAM believing it is GOS — wrong data presented as right.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    w._current_image = np.ones((4, 4))
    w._on_compute_error("boom", w._compute_generation)
    assert w._current_image is None, "stale image survived a failed computation"


def test_line_mode_accepts_toggled_bool(qtbot):
    """The toolbar connects QAction.toggled(bool) to this slot. The old
    zero-argument signature made every click raise TypeError inside the event
    loop — the Line Profile button was silently dead in the shipped app."""
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    w.toggle_line_mode(True)
    assert w._line_mode is True
    w.toggle_line_mode(False)
    assert w._line_mode is False
    # argument-less call still toggles (keyboard/debug path)
    w.toggle_line_mode()
    assert w._line_mode is True


def test_boundary_overlay_accepts_float_mask(qtbot):
    """Issue #9: "je ne vois ni les grains parents ni les joints de grains".

    grain_boundary_map() returns float64 (it goes through _to_grid, which needs a
    float fill), but the overlay used it directly as a boolean index, raising
    IndexError inside a Qt slot on EVERY draw — so the boundary checkbox silently
    did nothing. Only the session log surfaced it.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    class _FakeMap:
        shape = (6, 8)

        def grain_boundary_map(self):
            m = np.zeros(self.shape, dtype=np.float64)
            m[2, :] = 1.0
            return m

    w = MapViewer()
    qtbot.addWidget(w)
    w._ebsd_map = _FakeMap()
    w._boundary_visible = True
    w._update_boundary()  # must not raise

    rgba = w._boundary_item.image
    assert rgba is not None
    assert rgba[2, 0, 3] > 0.0, "boundary row not painted"
    assert rgba[0, 0, 3] == 0.0, "non-boundary pixel painted"


def test_computing_overlay_paints_its_scrim(qtbot):
    """The overlay has a dark scrim in SCSS, but a QLabel parented to a
    QGraphicsView will not paint a stylesheet background without
    WA_StyledBackground — so the text sat directly on the grain map."""
    from PySide6.QtCore import Qt

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    assert w._computing_overlay.testAttribute(
        Qt.WidgetAttribute.WA_StyledBackground
    ), "overlay will not paint its background over the map"


def test_categorical_legend_for_few_categories(qtbot):
    """Packet/Block/Variant maps shipped four flat colours and no key."""
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)

    w._update_category_legend(np.array([[0, 1], [2, 3]], dtype=float), "Packet")
    assert w._legend_label.isVisibleTo(w)
    html = w._legend_label.text()
    assert "Packet" in html
    for cat in ("0", "1", "2", "3"):
        assert f">{cat}<" in html or f" {cat}<" in html

    # thousands of parent grains: a legend would be noise, so hide it
    w._update_category_legend(np.arange(500, dtype=float).reshape(20, 25), "Parent Grain ID")
    assert not w._legend_label.isVisibleTo(w)
