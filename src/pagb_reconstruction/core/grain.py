import numpy as np
from pydantic import ConfigDict
from scipy import ndimage

from pagb_reconstruction.core.base import SpatialRegion


class Grain(SpatialRegion):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    mean_quaternion: np.ndarray  # (4,) quaternion
    phase_id: int
    area: int
    neighbor_ids: list[int] = []

    @property
    def size(self) -> int:
        return len(self.pixel_indices)


def detect_grains(
    quaternions: np.ndarray,
    phase_ids: np.ndarray,
    shape: tuple[int, int],
    symmetry_quats: np.ndarray,
    threshold_deg: float = 5.0,
    min_size: int = 5,
) -> list[Grain]:
    from pagb_reconstruction.utils.math_ops import misorientation_angle_neighbors

    rows, cols = shape
    n_pixels = rows * cols

    misori_h, misori_v = misorientation_angle_neighbors(
        quaternions, shape, symmetry_quats
    )

    boundary_h = misori_h >= threshold_deg
    boundary_v = misori_v >= threshold_deg

    label_map = np.zeros(n_pixels, dtype=np.int32)
    labeled_2d = np.zeros((rows, cols), dtype=np.int32)

    connectivity = np.ones((3, 3), dtype=np.int32)
    phase_map_2d = phase_ids.reshape(rows, cols)

    current_label = 0
    unique_phases = np.unique(phase_ids)

    for ph in unique_phases:
        phase_mask = phase_map_2d == ph
        not_boundary = np.ones((rows, cols), dtype=bool)
        not_boundary[:, 1:] &= (
            ~boundary_h.reshape(rows, cols - 1)
            if boundary_h.size == rows * (cols - 1)
            else ~boundary_h.reshape(rows, cols)[:, 1:]
        )
        not_boundary[1:, :] &= (
            ~boundary_v.reshape(rows - 1, cols)
            if boundary_v.size == (rows - 1) * cols
            else ~boundary_v.reshape(rows, cols)[1:, :]
        )

        connected = phase_mask & not_boundary
        labels, n_features = ndimage.label(connected, structure=connectivity)

        for i in range(1, n_features + 1):
            mask = labels == i
            pixels = np.where(mask.ravel())[0]
            if len(pixels) < min_size:
                continue
            current_label += 1
            labeled_2d[mask] = current_label
            label_map[pixels] = current_label

    grains: list[Grain] = []
    for grain_id in range(1, current_label + 1):
        pixels = np.where(label_map == grain_id)[0]
        if len(pixels) == 0:
            continue
        q = quaternions[pixels]
        mean_q = q.mean(axis=0)
        mean_q /= np.linalg.norm(mean_q)
        ph_id = int(phase_ids[pixels[0]])
        grains.append(
            Grain(
                id=grain_id,
                pixel_indices=pixels,
                mean_quaternion=mean_q,
                phase_id=ph_id,
                area=len(pixels),
            )
        )

    _compute_neighbors(grains, labeled_2d, shape)
    return grains


def _compute_neighbors(
    grains: list[Grain], labeled_2d: np.ndarray, shape: tuple[int, int]
):
    rows, cols = shape
    grain_map = {g.id: g for g in grains}

    for r in range(rows):
        for c in range(cols):
            gid = labeled_2d[r, c]
            if gid == 0:
                continue
            for dr, dc in [(0, 1), (1, 0)]:
                nr, nc = r + dr, c + dc
                if nr >= rows or nc >= cols:
                    continue
                nid = labeled_2d[nr, nc]
                if nid == 0 or nid == gid:
                    continue
                g = grain_map.get(gid)
                if g is None:
                    continue
                if nid not in g.neighbor_ids:
                    g.neighbor_ids.append(nid)
                    n = grain_map.get(nid)
                    if n is not None:
                        n.neighbor_ids.append(gid)
