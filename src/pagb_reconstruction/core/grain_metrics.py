from typing import Literal

import numpy as np

from pagb_reconstruction.core.base import Displayable


class GrainSizeResult(Displayable):
    mean_intercept_um: float
    astm_grain_size_number: float
    total_crossings: int
    total_line_length_um: float
    equivalent_diameter_um: float
    grain_count: int
    method: str


class GrainMetrics(Displayable):
    method: Literal["area", "intercept"] = "intercept"
    n_lines: int = 50
    step_size_um: float = 1.0

    def measure(self, grain_map: np.ndarray, step_size: float = 0.0):
        step = step_size if step_size > 0 else self.step_size_um
        if self.method == "intercept":
            return self._intercept(grain_map, step)
        return self._area(grain_map, step)

    def _intercept(self, grain_map: np.ndarray, step: float):
        h, w = grain_map.shape
        total_cross = 0
        total_len = 0.0
        for y in np.linspace(0, h - 1, self.n_lines, dtype=int):
            line = grain_map[y, :]
            crossings = int(np.sum(line[1:] != line[:-1]))
            if crossings >= 3:
                total_cross += crossings
                total_len += w * step
        for x in np.linspace(0, w - 1, self.n_lines, dtype=int):
            line = grain_map[:, x]
            crossings = int(np.sum(line[1:] != line[:-1]))
            if crossings >= 3:
                total_cross += crossings
                total_len += h * step
        mean_int = total_len / max(total_cross, 1)
        mean_mm = mean_int / 1000
        astm = -6.6457 * np.log2(max(mean_mm, 1e-6)) - 3.298
        return GrainSizeResult(
            mean_intercept_um=mean_int,
            astm_grain_size_number=astm,
            total_crossings=total_cross,
            total_line_length_um=total_len,
            equivalent_diameter_um=0.0,
            grain_count=len(np.unique(grain_map)),
            method="intercept",
        )

    def _area(self, grain_map: np.ndarray, step: float):
        ids, counts = np.unique(grain_map, return_counts=True)
        areas = counts * step * step
        eq_diams = 2 * np.sqrt(areas / np.pi)
        mean_diam = float(eq_diams.mean())
        mean_mm = mean_diam / 1000
        astm = -6.6457 * np.log2(max(mean_mm, 1e-6)) - 3.298
        return GrainSizeResult(
            mean_intercept_um=mean_diam,
            astm_grain_size_number=astm,
            total_crossings=0,
            total_line_length_um=0.0,
            equivalent_diameter_um=mean_diam,
            grain_count=len(ids),
            method="area",
        )
