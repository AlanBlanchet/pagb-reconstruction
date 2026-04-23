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
    bcc_dirs: np.ndarray = np.array(
        [[1, -1, 1], [1, 1, -1], [-1, 1, 1], [1, 1, 1], [1, -1, 1], [1, 1, -1]],
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
