import numpy as np


def remap_labels(labels: np.ndarray) -> np.ndarray:
    unique = np.unique(labels)
    remap = {old: new for new, old in enumerate(unique)}
    return np.array([remap[l] for l in labels], dtype=np.int32)


def boundaries_from_2d(arr: np.ndarray) -> np.ndarray:
    rows, cols = arr.shape
    boundary = np.zeros((rows, cols), dtype=bool)
    boundary[:, :-1] |= arr[:, :-1] != arr[:, 1:]
    boundary[:-1, :] |= arr[:-1, :] != arr[1:, :]
    return boundary


def align_hemisphere(quats: np.ndarray, ref: np.ndarray) -> np.ndarray:
    aligned = quats.copy()
    for k in range(len(aligned)):
        if np.dot(aligned[k], ref) < 0:
            aligned[k] = -aligned[k]
    return aligned


def grain_index_map(grains) -> dict[int, int]:
    return {g.id: idx for idx, g in enumerate(grains)}
