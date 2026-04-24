import numpy as np
from pydantic import Field
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from pagb_reconstruction.core.base import SpatialRegion
from pagb_reconstruction.utils.math_ops import MisorientationOps


class Grain(SpatialRegion):
    id: int
    mean_quaternion: np.ndarray  # (4,) quaternion
    phase_id: int
    area: int
    pixel_rc: np.ndarray  # (N, 2) row-col for each pixel
    neighbor_ids: list[int] = Field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.pixel_indices)

    @property
    def equivalent_diameter(self) -> float:
        return 2 * np.sqrt(self.area / np.pi)

    @property
    def row_col(self) -> tuple[np.ndarray, np.ndarray]:
        return self.pixel_rc[:, 0], self.pixel_rc[:, 1]

    @property
    def aspect_ratio(self) -> float:
        if self.area < 3:
            return 1.0
        r, c = self.row_col
        cov = np.cov(np.column_stack([c, r]).T)
        eigvals = np.sort(np.linalg.eigvalsh(cov))[::-1]
        return float(np.sqrt(eigvals[0] / max(eigvals[1], 1e-12)))

    @property
    def perimeter(self) -> int:
        rows, cols = self.row_col
        pixel_set = set(zip(rows, cols))
        count = 0
        for r, c in pixel_set:
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                if (r + dr, c + dc) not in pixel_set:
                    count += 1
                    break
        return count


def detect_grains(
    quaternions: np.ndarray,
    phase_ids: np.ndarray,
    topology,
    symmetry_quats: np.ndarray,
    threshold_deg: float = 5.0,
    min_size: int = 5,
) -> list[Grain]:
    from pagb_reconstruction.core.ebsd_map import PixelTopology

    topo: PixelTopology = topology
    pairs = topo.pairs
    angles = MisorientationOps.pairs(quaternions, pairs, symmetry_quats)
    same_phase = phase_ids[pairs[:, 0]] == phase_ids[pairs[:, 1]]
    keep = (angles < threshold_deg) & same_phase

    kept = pairs[keep]
    n = topo.n_pixels
    data = np.ones(len(kept) * 2, dtype=np.float32)
    rows = np.concatenate([kept[:, 0], kept[:, 1]])
    cols_arr = np.concatenate([kept[:, 1], kept[:, 0]])
    adj = coo_matrix((data, (rows, cols_arr)), shape=(n, n))

    n_comp, labels = connected_components(adj, directed=False)

    label_sizes = np.bincount(labels, minlength=n_comp)
    valid_labels = np.where(label_sizes >= min_size)[0]

    remap = np.full(n_comp, -1, dtype=np.int32)
    for new_id, old_id in enumerate(valid_labels, start=1):
        remap[old_id] = new_id

    pixel_labels = remap[labels]

    grains: list[Grain] = []
    for grain_id in range(1, len(valid_labels) + 1):
        pixels = np.where(pixel_labels == grain_id)[0]
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
                pixel_rc=topo.pixel_to_rc[pixels],
            )
        )

    _compute_neighbors(grains, pixel_labels, pairs)
    return grains


def _compute_neighbors(
    grains: list[Grain], pixel_labels: np.ndarray, pairs: np.ndarray
):
    grain_map = {g.id: g for g in grains}
    for k in range(pairs.shape[0]):
        gid_a = pixel_labels[pairs[k, 0]]
        gid_b = pixel_labels[pairs[k, 1]]
        if gid_a <= 0 or gid_b <= 0 or gid_a == gid_b:
            continue
        ga = grain_map.get(gid_a)
        gb = grain_map.get(gid_b)
        if ga is not None and gid_b not in ga.neighbor_ids:
            ga.neighbor_ids.append(gid_b)
        if gb is not None and gid_a not in gb.neighbor_ids:
            gb.neighbor_ids.append(gid_a)
