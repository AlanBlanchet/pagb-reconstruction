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


