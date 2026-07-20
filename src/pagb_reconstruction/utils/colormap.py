from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from orix.plot import IPFColorKeyTSL
from orix.quaternion import Orientation, Symmetry
from orix.vector import Vector3d

if TYPE_CHECKING:
    # Only a type annotation below — importing at runtime would create a cycle
    # (core.phase → core → utils.colormap), so colormap stays core-free.
    from pagb_reconstruction.core.phase import PhaseConfig

DEFAULT_IPF_DIRECTION = Vector3d.zvector()

_IPF_KEY_IMAGE_CACHE: dict[tuple[str, tuple[float, float, float]], np.ndarray] = {}


def ipf_color_key(
    symmetry: Symmetry, direction: Vector3d | None = None
) -> IPFColorKeyTSL:
    return IPFColorKeyTSL(symmetry, direction=direction or DEFAULT_IPF_DIRECTION)


def ipf_key_image(
    symmetry: Symmetry, direction: Vector3d | None = None, size_px: int = 200
) -> np.ndarray:
    """Render the inverse-pole-figure colour-key triangle (with crystal-direction
    corner labels) to an RGBA uint8 image. Cached per symmetry + direction."""
    d = direction or DEFAULT_IPF_DIRECTION
    cache_key = (symmetry.name, tuple(np.round(d.data.flatten(), 3)))
    cached = _IPF_KEY_IMAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    fig = ipf_color_key(symmetry, d).plot(return_figure=True)
    fig.set_size_inches(size_px / 100, size_px / 100)
    fig.set_dpi(100)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    w, h = canvas.get_width_height()
    img = np.frombuffer(canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4).copy()
    plt.close(fig)
    _IPF_KEY_IMAGE_CACHE[cache_key] = img
    return img


def ipf_colors(
    orientations: Orientation, direction: Vector3d | None = None
) -> np.ndarray:
    key = ipf_color_key(orientations.symmetry, direction)
    return key.orientation2color(orientations)


def phase_colormap(phase_ids: np.ndarray, phases: list[PhaseConfig]) -> np.ndarray:
    n = len(phase_ids)
    colors = np.zeros((n, 3), dtype=np.float32)

    for phase in phases:
        mask = phase_ids == phase.phase_id
        rgb = _hex_to_rgb(phase.color)
        colors[mask] = rgb

    return colors


def _hex_to_rgb(hex_color: str) -> np.ndarray:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return np.array([r, g, b], dtype=np.float32)
