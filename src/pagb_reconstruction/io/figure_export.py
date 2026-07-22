"""Export a map as a publication-ready figure.

The previous export dumped the raw plot widget: no scale bar the reader could
trust, no colour key, and PNG/SVG only. Issue #11 asked for "png, jpg ou svg avec
légende et échelle".

matplotlib is already a dependency and handles all three formats, a real
colourbar, and vector output for papers.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

_MAX_LEGEND_CATEGORIES = 24


def nice_scale_length(width_um: float) -> float:
    """A round scale-bar length (1, 2 or 5 x a power of ten) under ~1/4 of the map.

    A bar labelled "3.7 µm" is unreadable; scientific figures use round numbers.
    """
    if width_um <= 0:
        return 1.0
    target = width_um / 4.0
    exponent = np.floor(np.log10(target))
    base = 10.0**exponent
    for multiple in (5.0, 2.0, 1.0):
        if multiple * base <= target:
            return float(multiple * base)
    return float(base)


def _draw_scale_bar(ax, n_cols: int, dx: float):
    """Scale bar sized from the real step, drawn over the bottom-right corner."""
    width_um = n_cols * dx
    bar_um = nice_scale_length(width_um)
    bar_px = bar_um / dx if dx else 0
    if bar_px <= 0:
        return

    bottom = max(ax.get_ylim())  # imshow puts row 0 at the top, so this is the base
    height = max(1.5, n_cols * 0.008)
    margin = height * 2.5

    # Bottom-LEFT, matching the reference OIM exports and the live viewer bar
    # (and clear of the colour bar, which sits on the right).
    x0 = n_cols * 0.03
    x1 = x0 + bar_px
    bar_y = bottom - margin - height

    ax.add_patch(Rectangle((x0, bar_y), bar_px, height, color="white", zorder=5))
    # Label sits clear ABOVE the bar; va="bottom" anchors its baseline there.
    ax.text(
        (x0 + x1) / 2,
        bar_y - height * 1.2,
        f"{bar_um:g} µm",
        color="white",
        ha="center",
        va="bottom",
        fontsize=9,
        zorder=5,
        bbox={"facecolor": "black", "alpha": 0.55, "pad": 2.0, "edgecolor": "none"},
    )


def _draw_parent_segments(ax, segments):
    """Bold black parent-grain outlines, aligned to pixel boundaries.

    ``segments`` is ``(xs, ys)`` of endpoint PAIRS in map (x, y) where an edge
    between pixels ``c`` and ``c+1`` sits at ``x = c+1``. imshow centres pixel
    ``c`` at ``x = c``, so that same boundary is at ``x = c+0.5`` — shift by
    -0.5 to land the line exactly on the pixel seam.
    """
    xs, ys = segments
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if xs.size == 0:
        return
    ax.plot(
        xs.reshape(-1, 2).T - 0.5,
        ys.reshape(-1, 2).T - 0.5,
        color="black",
        linewidth=1.1,
        solid_capstyle="round",
        zorder=4,
    )


def export_map_figure(
    path,
    image: np.ndarray,
    title: str = "",
    step_size: tuple[float, float] = (1.0, 1.0),
    unit: str = "",
    colormap: str = "viridis",
    categorical: bool = False,
    parent_segments: tuple[np.ndarray, np.ndarray] | None = None,
) -> Path:
    """Write ``image`` as a figure with a scale bar and the right colour key.

    ``step_size`` is (dy, dx) in micrometres, matching :attr:`EBSDMap.step_size`,
    so the scale bar and the aspect ratio reflect the real scan geometry rather
    than the pixel grid.
    """
    path = Path(path)
    data = np.asarray(image)
    dy, dx = float(step_size[0] or 1.0), float(step_size[1] or 1.0)
    n_rows, n_cols = data.shape[0], data.shape[1]

    # Physical extent keeps a non-square step (hex scans) from distorting the map.
    fig_w = 7.0
    fig_h = max(2.0, fig_w * (n_rows * dy) / max(n_cols * dx, 1e-9))
    fig, ax = plt.subplots(figsize=(fig_w, min(fig_h, 12.0)), dpi=200)

    is_rgb = data.ndim == 3 and data.shape[2] in (3, 4)
    if is_rgb:
        shown = np.clip(data, 0, 1) if data.dtype.kind == "f" else data
        ax.imshow(shown, interpolation="nearest", aspect=dy / dx)
    elif categorical:
        finite = data[np.isfinite(data)]
        cats = np.unique(finite[finite >= 0]).astype(int) if finite.size else np.array([])
        cmap = plt.get_cmap("tab20")
        ax.imshow(
            np.where(np.isfinite(data), data % 20, np.nan),
            cmap=cmap, vmin=0, vmax=19, interpolation="nearest", aspect=dy / dx,
        )
        if 0 < cats.size <= _MAX_LEGEND_CATEGORIES:
            ax.legend(
                handles=[
                    Patch(facecolor=cmap((int(c) % 20) / 19.0), label=str(int(c)))
                    for c in cats
                ],
                title=title or "Category",
                loc="center left",
                bbox_to_anchor=(1.02, 0.5),
                frameon=False,
                fontsize=8,
            )
    else:
        im = ax.imshow(data, cmap=colormap, interpolation="nearest", aspect=dy / dx)
        bar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
        if unit:
            bar.set_label(unit)

    if parent_segments is not None:
        _draw_parent_segments(ax, parent_segments)

    _draw_scale_bar(ax, n_cols, dx)
    if title:
        ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
