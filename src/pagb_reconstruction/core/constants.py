import numpy as np
from pydantic import BaseModel, ConfigDict


class BoundaryThresholds(BaseModel):
    grain_angle_deg: float = 5.0


class CSLParams(BaseModel):
    sigma3_angle: float = 60.0
    sigma3_tolerance: float = 8.66
    sigma3_axis: tuple[int, int, int] = (1, 1, 1)
    sigma9_angle: float = 38.94
    sigma9_tolerance: float = 5.0
    sigma9_axis: tuple[int, int, int] = (1, 1, 0)
    axis_dot_threshold: float = 0.9
    low_angle_threshold: float = 2.0
    high_angle_threshold: float = 15.0


class SlipSystems(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    bcc_planes: np.ndarray = np.array(
        [[1, 1, 0], [1, 0, 1], [0, 1, 1], [1, -1, 0], [1, 0, -1], [0, 1, -1]],
        dtype=np.float64,
    )
    # <111> slip directions, each lying IN its {110} plane (n . d == 0). Systems
    # 2 and 5 previously used directions with n . d = 2, which is geometrically
    # impossible and let the Schmid factor exceed its 0.5 maximum.
    bcc_dirs: np.ndarray = np.array(
        [[1, -1, 1], [1, 1, -1], [1, 1, -1], [1, 1, 1], [1, -1, 1], [1, 1, 1]],
        dtype=np.float64,
    )
    fcc_planes: np.ndarray = np.array(
        [[1, 1, 1], [1, 1, 1], [1, 1, 1], [1, -1, 1], [1, -1, 1], [1, -1, 1]],
        dtype=np.float64,
    )
    fcc_dirs: np.ndarray = np.array(
        [[1, -1, 0], [0, 1, -1], [-1, 0, 1], [1, 1, 0], [0, 1, 1], [-1, 0, 1]],
        dtype=np.float64,
    )


class ClusteringDefaults(BaseModel):
    inflation_power: float = 1.6
    expansion_power: int = 2
    max_iterations: int = 100
    convergence_threshold: float = 1e-5
    min_edge_weight: float = 0.01
    attractor_threshold: float = 0.01
    prune_threshold: float = 1e-5
    variant_inflation: float = 1.1
    variant_max_iter: int = 15


def slip_family(phase_name: str | None) -> str:
    """Slip-system family ("bcc" or "fcc") for a phase NAME.

    BCC and FCC are both point group m-3m with 48 operations, so the crystal
    symmetry cannot tell them apart — selecting on symmetry size handed every
    cubic phase the FCC systems. Steel defaults to bcc (ferrite / martensite).
    """
    name = (phase_name or "").lower()
    fcc_markers = ("fcc", "austenit", "gamma", "\u03b3")
    return "fcc" if any(m in name for m in fcc_markers) else "bcc"
