import numpy as np
from orix.plot import IPFColorKeyTSL
from orix.quaternion import Orientation, Symmetry
from orix.vector import Vector3d

from pagb_reconstruction.core.phase import PhaseConfig

DEFAULT_IPF_DIRECTION = Vector3d.zvector()


def ipf_color_key(
    symmetry: Symmetry, direction: Vector3d | None = None
) -> IPFColorKeyTSL:
    return IPFColorKeyTSL(symmetry, direction=direction or DEFAULT_IPF_DIRECTION)


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
