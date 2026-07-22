"""stat_plots — the extensible diagnostic-plot catalog behind the Statistics
browser. Adding a plot must be ONE catalog entry; each entry filters itself out
when its data is absent and builds a real widget when present."""

import numpy as np


def test_histogram_plot_available_only_with_values(qtbot):
    from pagb_reconstruction.ui.widgets.stat_plots import HistogramPlot, PlotContext

    with_data = HistogramPlot(
        key="x", title="X", category="Dist", x_label="v", y_label="n",
        values=lambda ctx: np.array([1.0, 2.0, 3.0, 4.0]),
    )
    empty = HistogramPlot(
        key="y", title="Y", category="Dist", x_label="v", y_label="n",
        values=lambda ctx: None,
    )
    ctx = PlotContext()
    assert with_data.available(ctx)
    assert not empty.available(ctx)
    w = with_data.build(ctx)
    qtbot.addWidget(w)
    assert w is not None


def test_catalog_keys_unique_and_well_formed():
    from pagb_reconstruction.ui.widgets.stat_plots import CATALOG

    assert len(CATALOG) >= 8, "the browser should offer many plots, not four"
    keys = [e.key for e in CATALOG]
    assert len(keys) == len(set(keys)), "plot keys must be unique"
    for e in CATALOG:
        assert e.key and e.title and e.category


def test_catalog_filters_to_available_and_builds_each(
    qtbot, variant_graph_result, sample_ebsd
):
    from pagb_reconstruction.ui.widgets.stat_plots import CATALOG, PlotContext

    ctx = PlotContext(result=variant_graph_result, ebsd_map=sample_ebsd, or_type="KS")
    available = [e for e in CATALOG if e.available(ctx)]
    assert len(available) >= 6, "a full reconstruction lights up most plots"
    keys = {e.key for e in available}
    assert {"parent_size_um", "fit_angles", "variants"} <= keys
    for e in available:
        w = e.build(ctx)
        qtbot.addWidget(w)
        assert w is not None


def test_no_plot_available_on_empty_context():
    from pagb_reconstruction.ui.widgets.stat_plots import CATALOG, PlotContext

    assert not any(e.available(PlotContext()) for e in CATALOG)


# ── degenerate / low-cardinality data must not render as one solid block ──
# visual-critic 2026-07-22: Fit angles (perfect fit → all zeros), Packets/Blocks
# (no hierarchy in the sample), Phase fractions (2 categories) each filled the
# whole plot with one colour instead of drawing discrete bars.


def test_histogram_of_one_value_shows_a_note_not_a_plot_filling_bar(qtbot):
    import pyqtgraph as pg

    from pagb_reconstruction.ui.widgets.stat_plots import HistogramPlot, PlotContext

    p = HistogramPlot(
        key="x", title="Fit", category="Quality", x_label="°", y_label="n",
        values=lambda ctx: np.zeros(50),  # a perfect fit: every value identical
    )
    w = p.build(PlotContext())
    qtbot.addWidget(w)
    bars = [it for it in w.plot_item.items if isinstance(it, pg.BarGraphItem)]
    texts = [it for it in w.plot_item.items if isinstance(it, pg.TextItem)]
    assert not bars, "a one-value histogram must not draw a plot-filling bar"
    assert texts, "it should say all values are equal instead"


def test_count_bar_with_one_category_sits_in_a_padded_range(qtbot):
    from pagb_reconstruction.ui.widgets.stat_plots import CountBarPlot, PlotContext

    p = CountBarPlot(
        key="c", title="Packets", category="Hierarchy", x_label="id", y_label="n",
        counts=lambda ctx: (np.array([0.0]), np.array([100.0])),
    )
    w = p.build(PlotContext())
    qtbot.addWidget(w)
    (x_lo, x_hi), _ = w.plot_item.viewRange()
    assert (x_hi - x_lo) > 1.5, "one bar must sit in a padded x-range, not fill it"
