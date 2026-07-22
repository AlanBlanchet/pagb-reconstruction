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
