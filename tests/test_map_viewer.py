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


def test_equalize_does_not_touch_categorical_ids(qtbot, sample_ebsd):
    """Histogram equalisation is a contrast transform for CONTINUOUS data.

    Applied to a categorical map (Phase / Packet / Block / Variant) it remaps the
    id values themselves before they are turned into palette indices, so a 2-phase
    map renders as banded rainbow noise instead of 2 colours. Equalising ids is
    meaningless — the numbers are labels, not intensities.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    w.set_ebsd_map(sample_ebsd)

    w._hist_eq_cb.setChecked(True)
    w._display_combo.setCurrentText("Phase")

    raw = sample_ebsd.compute_map_property("Phase")
    shown = w._image_item.image
    if raw.dtype in (np.float32, np.float64):
        raw = (np.clip(raw, 0, 1) * 255).astype(np.uint8)

    assert np.array_equal(shown, raw), (
        "equalisation altered a categorical Phase map — its colours are labels, "
        "not intensities, so the stretch must be skipped"
    )
    assert not w._hist_eq_cb.isEnabled(), (
        "Equalize must be disabled on a categorical map, not silently ignored — "
        "an enabled control that does nothing is a false affordance"
    )


def test_overlay_opacity_does_not_dilute_its_scrim(qtbot):
    """A looping opacity pulse multiplied the scrim alpha: a 0.94 background
    rendered at ~0.65 measured, dropping text contrast below the readable floor.
    The overlay must settle fully opaque."""
    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    assert w._overlay_anim.loopCount() == 1, "overlay must not pulse forever"
    assert w._overlay_anim.endValue() == 1.0
    assert w._overlay_opacity.opacity() == 1.0


def test_line_mode_announces_itself(qtbot):
    """Arming line-profile mode must be visible: a crosshair cursor over the
    map and a hint of what to do next. Without either, the armed mode is
    indistinguishable from a dead button — audited live as 'engages with no
    visible effect anywhere on screen'.
    """
    from PySide6.QtCore import Qt

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)

    w.toggle_line_mode(True)
    assert (
        w._graphics_view.viewport().cursor().shape() == Qt.CursorShape.CrossCursor
    ), "armed line mode must show a crosshair over the map"
    # isHidden(), not isVisible(): offscreen the ancestor view is never marked
    # visible, so isVisible() is false for every child regardless of state.
    assert not w._hint_label.isHidden(), "armed line mode must show its hint"
    assert "profile" in w._hint_label.text().lower(), (
        "the hint must say what to do next"
    )

    w.toggle_line_mode(False)
    assert (
        w._graphics_view.viewport().cursor().shape() != Qt.CursorShape.CrossCursor
    ), "disarming must restore the normal cursor"
    assert w._hint_label.isHidden()


def test_completing_a_line_profile_clears_its_armed_state(qtbot):
    """Finishing the two-click profile must disarm the mode VISIBLY.

    The handler sets _line_mode = False directly, bypassing toggle_line_mode, so
    the crosshair cursor and the "click two points" banner survived a completed
    profile and told the user the tool was still armed when it was not.
    """
    import numpy as np
    from PySide6.QtCore import Qt

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    class _FakeMap:
        shape = (8, 8)
        step_size = (1.0, 1.0)
        quaternions = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (64, 1))

        def _primary_symmetry_quats(self):
            return np.array([[1.0, 0.0, 0.0, 0.0]])

    w = MapViewer()
    qtbot.addWidget(w)
    w._ebsd_map = _FakeMap()

    w.toggle_line_mode(True)
    assert not w._hint_label.isHidden()

    w._handle_line_click(1, 1)   # first point

    # The profile opens a dialog; disarming must happen BEFORE that, or a modal
    # or slow dialog leaves the map looking armed while it is up.
    order = []
    real_profile = w._show_misorientation_profile
    real_disarm = w._disarm_line_mode

    def _profile(*a, **k):
        order.append("profile")
        return real_profile(*a, **k)

    def _disarm(*a, **k):
        order.append("disarm")
        return real_disarm(*a, **k)

    w._show_misorientation_profile = _profile
    w._disarm_line_mode = _disarm
    w._handle_line_click(5, 5)   # second point completes the profile
    assert order and order[0] == "disarm", (
        f"disarm must precede the profile dialog, got {order}"
    )

    assert w._line_mode is False
    assert w._hint_label.isHidden(), "hint banner survived a completed profile"
    assert (
        w._graphics_view.viewport().cursor().shape() != Qt.CursorShape.CrossCursor
    ), "crosshair survived a completed profile — the tool looks still armed"


def test_line_profile_draws_above_the_map(qtbot):
    """The measured line must be painted ABOVE the map and its overlays.

    Every other overlay sets an explicit z (boundary 10, highlight 11) but the
    line item was left at the default 0, so it rendered underneath the image —
    measured live as 0/250 pixel samples matching the line colour along the exact
    computed path, in every theme. The profile dialog still opened with correct
    data, which is why this looked like a coordinate bug and was not.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    class _FakeMap:
        shape = (8, 8)
        step_size = (1.0, 1.0)
        quaternions = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (64, 1))

        def _primary_symmetry_quats(self):
            return np.array([[1.0, 0.0, 0.0, 0.0]])

    w = MapViewer()
    qtbot.addWidget(w)
    w._ebsd_map = _FakeMap()

    w.toggle_line_mode(True)
    w._handle_line_click(1, 1)
    assert w._line_item is not None

    overlays = max(
        w._image_item.zValue(), w._boundary_item.zValue(), w._highlight_item.zValue()
    )
    assert w._line_item.zValue() > overlays, (
        f"line z={w._line_item.zValue()} is not above the map overlays "
        f"(max z={overlays}) — it paints underneath and is invisible"
    )


def test_highlighting_a_parent_actually_locates_it(qtbot):
    """The Parents panel says "select one to locate it", so selecting must move
    the view to it — not merely tint it in place.

    A worst-fit parent is typically the SMALLEST grain on the map (that is why
    it fits badly), so a tint under ~100px is invisible on a full-map view and
    the copy is a broken promise.
    """
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    rows, cols = 200, 200
    ids = np.full(rows * cols, -1, dtype=int)
    grid = ids.reshape(rows, cols)
    grid[150:158, 20:28] = 7          # a small grain, far from centre

    class _FakeMap:
        shape = (rows, cols)

        def _to_grid(self, flat, fill=-1):
            return np.asarray(flat).reshape(self.shape)

    class _FakeResult:
        parent_grain_ids = ids

    w = MapViewer()
    qtbot.addWidget(w)
    w._ebsd_map = _FakeMap()
    w._result = _FakeResult()
    w._image_item.setImage(np.zeros((rows, cols), dtype=np.float32))
    w._plot.getViewBox().autoRange(padding=0)
    before = w._plot.getViewBox().viewRange()

    w.highlight_parent(7)

    after = w._plot.getViewBox().viewRange()
    assert after != before, "selecting a parent did not move the view to it"

    (x0, x1), (y0, y1) = after
    assert x0 <= 24 <= x1 and y0 <= 154 <= y1, (
        f"grain centre (24,154) not inside the new view {after}"
    )
    assert (x1 - x0) < cols, "view did not zoom in at all — grain stays tiny"


def test_export_hides_interactive_decorations(qtbot, tmp_path):
    """Issue #13: the saved image carried the selection crosshair. Decorations
    are session state, not data — they must not appear in an export, and must
    come back afterwards."""
    import numpy as np

    from pagb_reconstruction.ui.widgets.map_viewer import MapViewer

    w = MapViewer()
    qtbot.addWidget(w)
    w._image_item.setImage(np.random.default_rng(0).random((40, 60, 3)))
    w._crosshair_h.setVisible(True)
    w._crosshair_v.setVisible(True)

    seen = {}
    real_export = w.export_image

    import pyqtgraph as pg

    class SpyExporter:
        def __init__(self, plot):
            seen["crosshair_during"] = w._crosshair_h.isVisible()

        def export(self, path):
            pass

    orig = pg.exporters.ImageExporter
    pg.exporters.ImageExporter = SpyExporter
    try:
        real_export(str(tmp_path / "out.png"))
    finally:
        pg.exporters.ImageExporter = orig

    assert seen["crosshair_during"] is False, "crosshair rendered into the export"
    assert w._crosshair_h.isVisible(), "crosshair not restored after export"
