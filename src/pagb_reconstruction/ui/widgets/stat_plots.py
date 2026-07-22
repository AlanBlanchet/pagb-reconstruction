"""stat_plots — the extensible catalog of diagnostic plots.

Every chart the Statistics browser shows is ONE entry in ``CATALOG``. Adding a
plot is a single ``StatPlot`` — the browser groups it, lists it, and gives it the
whole panel when selected. No layout surgery, no squeezing a new chart into a
fixed row (Alan: "we could have many other different plots").

A plot is host-agnostic: each ``build`` returns a fresh ``QWidget`` (a themed
pyqtgraph ``StyledPlot`` for distributions, a matplotlib canvas for the pole
figure), so a plot owns its own rendering tech while the browser stays generic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult
from pagb_reconstruction.ui.plotting import StyledPlot
from pagb_reconstruction.ui.theme import active_theme


@dataclass(frozen=True)
class PlotContext:
    """Everything the catalog plots read, bundled once per reconstruction."""

    result: ReconstructionResult | None = None
    ebsd_map: EBSDMap | None = None
    or_type: str = ""

    @property
    def parent_orientations(self) -> np.ndarray | None:
        r = self.result
        return getattr(r, "parent_orientations", None) if r is not None else None

    @property
    def child_orientations(self) -> np.ndarray | None:
        e = self.ebsd_map
        return getattr(e, "quaternions", None) if e is not None else None


# ── extractors: PlotContext → sample values / (categories, counts) ──
# Module-level so each is unit-testable without a widget.


def _parent_ecd_um(ctx: PlotContext) -> np.ndarray | None:
    r, e = ctx.result, ctx.ebsd_map
    if r is None or e is None:
        return None
    labelled = r.parent_grain_ids[r.parent_grain_ids >= 0]
    if labelled.size == 0:
        return None
    dy, dx = e.step_size
    areas = np.bincount(labelled) * dx * dy
    areas = areas[areas > 0]
    return np.sqrt(4.0 * areas / np.pi)


def _child_ecd_um(ctx: PlotContext) -> np.ndarray | None:
    e = ctx.ebsd_map
    if e is None or not getattr(e, "grains", None):
        return None
    dy, dx = e.step_size
    scale = float(np.sqrt(dx * dy))  # px equivalent-diameter → µm
    return np.array([g.equivalent_diameter * scale for g in e.grains], dtype=float)


def _aspect_ratios(ctx: PlotContext) -> np.ndarray | None:
    e = ctx.ebsd_map
    if e is None or not getattr(e, "grains", None):
        return None
    return np.array([g.aspect_ratio for g in e.grains], dtype=float)


def _fit_angles(ctx: PlotContext) -> np.ndarray | None:
    r = ctx.result
    if r is None:
        return None
    v = r.fit_angles[~np.isnan(r.fit_angles)]
    return v if v.size else None


def _counts_of(field: str) -> Callable[[PlotContext], tuple[np.ndarray, np.ndarray] | None]:
    def _extract(ctx: PlotContext):
        r = ctx.result
        if r is None:
            return None
        vals = getattr(r, field, None)
        if vals is None:
            return None
        valid = vals[vals >= 0]
        if valid.size == 0:
            return None
        unique, counts = np.unique(valid, return_counts=True)
        return unique.astype(float), counts.astype(float)

    return _extract


def _phase_fractions(ctx: PlotContext) -> tuple[np.ndarray, np.ndarray] | None:
    e = ctx.ebsd_map
    if e is None:
        return None
    ph = e.phase_ids
    ids = [p.phase_id for p in e.phases]
    counts = np.array([float(np.sum(ph == pid)) for pid in ids])
    if counts.sum() == 0:
        return None
    return np.array(ids, dtype=float), counts


def _pad_x_range(host: StyledPlot, x: np.ndarray, width: float) -> None:
    """Give bars a padded x-range so a single / few bars read as DISCRETE bars,
    not one block stretched across the whole plot — the degenerate / low-
    cardinality case (a perfect fit, a sample with no packet hierarchy, a
    two-phase map). pyqtgraph otherwise auto-ranges tight to the lone bar."""
    lo, hi = float(np.min(x)), float(np.max(x))
    span = (hi - lo) or 1.0
    host.plot_item.setXRange(lo - width - 0.1 * span, hi + width + 0.1 * span, padding=0)


def _note(host: StyledPlot, text: str) -> None:
    """A centered message for a plot whose data has nothing to distribute."""
    label = pg.TextItem(text, color=active_theme().text_muted, anchor=(0.5, 0.5))
    host.plot_item.addItem(label)
    host.plot_item.setXRange(0, 1, padding=0)
    host.plot_item.setYRange(0, 1, padding=0)
    label.setPos(0.5, 0.5)


# ── plot kinds: generic, config-driven ──


@dataclass(frozen=True)
class HistogramPlot:
    """A distribution: bin raw sample values into a bar histogram."""

    key: str
    title: str
    category: str
    x_label: str
    y_label: str
    values: Callable[[PlotContext], np.ndarray | None]
    color: str = "accent"
    bins: int = 40

    def available(self, ctx: PlotContext) -> bool:
        v = self.values(ctx)
        return v is not None and len(v) > 0

    def build(self, ctx: PlotContext) -> QWidget:
        host = StyledPlot(self.title, x_label=self.x_label, y_label=self.y_label)
        v = self.values(ctx)
        if v is not None and len(v):
            uniq = np.unique(v)
            if len(uniq) <= 1:
                # A histogram of one value is meaningless — say so, don't stretch
                # a lone bar across the whole plot.
                _note(host, f"all {len(v)} values ≈ {float(uniq[0]):.3g}")
            else:
                n_bins = min(self.bins, len(uniq))
                hist, edges = np.histogram(v, bins=n_bins)
                x = (edges[:-1] + edges[1:]) / 2
                width = (edges[1] - edges[0]) * 0.9
                host.plot_bars(x, hist.astype(float), width=width,
                               color=getattr(active_theme(), self.color))
                _pad_x_range(host, x, width)
        return host


@dataclass(frozen=True)
class CountBarPlot:
    """A categorical bar chart from (categories, counts)."""

    key: str
    title: str
    category: str
    x_label: str
    y_label: str
    counts: Callable[[PlotContext], tuple[np.ndarray, np.ndarray] | None]
    color: str = "info"

    def available(self, ctx: PlotContext) -> bool:
        return self.counts(ctx) is not None

    def build(self, ctx: PlotContext) -> QWidget:
        host = StyledPlot(self.title, x_label=self.x_label, y_label=self.y_label)
        data = self.counts(ctx)
        if data is not None:
            x, heights = data
            host.plot_bars(x, heights, width=0.8,
                           color=getattr(active_theme(), self.color))
            _pad_x_range(host, x, 0.8)
        return host


@dataclass(frozen=True)
class WidgetPlot:
    """An entry backed by a bespoke widget (pole figure, spectrum) that owns its
    own rendering + controls. ``factory`` builds and feeds it."""

    key: str
    title: str
    category: str
    factory: Callable[[PlotContext], QWidget]
    is_available: Callable[[PlotContext], bool]

    def available(self, ctx: PlotContext) -> bool:
        return self.is_available(ctx)

    def build(self, ctx: PlotContext) -> QWidget:
        return self.factory(ctx)


StatPlot = HistogramPlot | CountBarPlot | WidgetPlot


# ── widget-plot factories (lazy imports keep this module cycle-free) ──


def _build_pole_figure(ctx: PlotContext) -> QWidget:
    from pagb_reconstruction.ui.widgets.pole_figure import PoleFigureWidget
    from pagb_reconstruction.ui.widgets.wheel_guard import install_wheel_guard

    w = PoleFigureWidget()
    w.set_orientations(child=ctx.child_orientations, parent=ctx.parent_orientations)
    install_wheel_guard(w)  # its plane/mode combos must not wheel-mutate on hover
    return w


def _build_spectrum(ctx: PlotContext) -> QWidget:
    from pagb_reconstruction.ui.widgets.misorientation_panel import MisorientationPanel

    w = MisorientationPanel()
    if ctx.ebsd_map is not None:
        w.set_ebsd_map(ctx.ebsd_map)
    if ctx.or_type:
        w.set_or_type(ctx.or_type)
    return w


# ── the catalog: one entry per plot; add a plot by adding a line ──

CATALOG: list[StatPlot] = [
    HistogramPlot("parent_size_um", "Parent grain size", "Distributions",
                  "ECD (µm)", "Count", _parent_ecd_um, color="accent"),
    HistogramPlot("child_size_um", "Child grain size", "Distributions",
                  "ECD (µm)", "Count", _child_ecd_um, color="info"),
    HistogramPlot("aspect_ratio", "Grain aspect ratio", "Distributions",
                  "Aspect ratio", "Count", _aspect_ratios, color="accent"),
    WidgetPlot("spectrum", "Misorientation spectrum", "Angular",
               _build_spectrum, lambda ctx: ctx.ebsd_map is not None),
    WidgetPlot("pole_figure", "Pole figure", "Angular", _build_pole_figure,
               lambda ctx: ctx.child_orientations is not None
               or ctx.parent_orientations is not None),
    HistogramPlot("fit_angles", "Fit angles", "Quality",
                  "Fit (°)", "Count", _fit_angles, color="success"),
    CountBarPlot("variants", "Variants", "Hierarchy",
                 "Variant ID", "Pixels", _counts_of("variant_ids"), color="info"),
    CountBarPlot("packets", "Packets", "Hierarchy",
                 "Packet ID", "Pixels", _counts_of("packet_ids"), color="accent"),
    CountBarPlot("blocks", "Blocks", "Hierarchy",
                 "Block ID", "Pixels", _counts_of("block_ids"), color="warning"),
    CountBarPlot("phase_fractions", "Phase fractions", "Composition",
                 "Phase ID", "Pixels", _phase_fractions, color="info"),
]
