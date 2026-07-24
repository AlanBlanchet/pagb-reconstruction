"""Headline numbers + the grain-size measurement tool, in their own panel.

Split out of Statistics: measured live, the stat cards plus this measurement
group consume more than the entire default bottom-dock height, so whichever
block went second never rendered. Capping the header at 180px instead hid the
Measure button behind ~800px of content. Neither block is small enough to budget
against the other.
"""


def test_summary_panel_owns_the_cards_and_measurement(qtbot):
    from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel

    p = SummaryPanel()
    qtbot.addWidget(p)
    assert p._measure_btn is not None
    assert p._card_parents is not None


def test_measure_click_emits_drawable_overlay(qtbot, sample_ebsd, variant_graph_result):
    from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel

    p = SummaryPanel()
    qtbot.addWidget(p)
    captured = {}
    p.measurement_overlay.connect(
        lambda lines, xs, ys: captured.update(lines=lines, xs=xs, ys=ys)
    )
    p.update_stats(variant_graph_result, ebsd_map=sample_ebsd)  # auto-run: no draw
    assert not captured, "a fresh reconstruction must not force-draw test lines"
    p._run_measurement(draw=True)  # explicit Measure click
    assert captured.get("lines"), "clicking Measure must emit test lines to draw"
    assert len(captured["xs"]) == len(captured["ys"])


def test_editing_settings_marks_the_measurement_stale(
    qtbot, sample_ebsd, variant_graph_result
):
    # finding B: changing "Test lines" left the old number shown with no cue
    from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel

    p = SummaryPanel()
    qtbot.addWidget(p)
    cleared = []
    p.measurement_cleared.connect(lambda: cleared.append(True))
    p.update_stats(variant_graph_result, ebsd_map=sample_ebsd)
    p._run_measurement(draw=True)  # a number is shown + lines drawn
    cleared.clear()
    p._metrics_form._field_widgets["n_lines"].setValue(33)  # edit a setting
    assert cleared, "editing a setting must clear the now-stale overlay"
    assert "Measure" in p._metrics_label.text(), "and prompt to re-measure"


def test_area_method_readout_uses_area_wording_not_crossings(
    qtbot, sample_ebsd, variant_graph_result
):
    # critic finding #1: area method reused the intercept template → showed an
    # alarming "0 crossings over 0.0 µm"
    from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel

    p = SummaryPanel()
    qtbot.addWidget(p)
    p.update_stats(variant_graph_result, ebsd_map=sample_ebsd)
    p._metrics_form._field_widgets["method"].setCurrentText("area")
    p._run_measurement(draw=True)
    txt = p._metrics_label.text().lower()
    assert "grain size" in txt, "area readout must say grain size, not intercept"
    assert "crossings" not in txt, "area readout must not show intercept crossings"


def test_test_lines_field_disabled_for_area_method(qtbot):
    # critic finding #2: "Test lines" has no effect for the area method
    from pagb_reconstruction.ui.widgets.summary_panel import SummaryPanel

    p = SummaryPanel()
    qtbot.addWidget(p)
    n_lines = p._metrics_form._field_widgets["n_lines"]
    assert n_lines.isEnabled(), "enabled by default (intercept)"
    p._metrics_form._field_widgets["method"].setCurrentText("area")
    assert not n_lines.isEnabled(), "Test lines does nothing for area — disable it"
    p._metrics_form._field_widgets["method"].setCurrentText("intercept")
    assert n_lines.isEnabled(), "re-enabled for intercept"
