from typing import Literal

import numpy as np
from pydantic import Field

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.utils.array_ops import line_intercepts


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
    n_lines: int = Field(default=20, ge=1, le=200, title="Test lines")

    # NB: no "step size" field — the pixel pitch is read from the loaded scan
    # header (EBSDMap.step_size), never typed by hand. An editable field here was
    # silently overridden by the map step, so "fixing" a wrong distance in it did
    # nothing (Eloïse, #15 "les distances ne sont pas les bonnes").

    def measure(
        self,
        grain_map: np.ndarray,
        step_size: tuple[float, float],
        ignore: int = -1,
    ) -> GrainSizeResult:
        """Mean grain size in µm. ``step_size`` is ``(dy, dx)`` — the map's
        ANISOTROPIC pixel pitch. A hexagonal EBSD scan has ``dx != dy`` (row
        pitch YSTEP = XSTEP·√3/2 ≈ 0.866·XSTEP), so applying one step to both
        axes scaled every distance wrong on real hex data (#15)."""
        dy, dx = step_size
        if self.method == "intercept":
            return self._intercept(grain_map, dy, dx, ignore)[0]
        return self._area(grain_map, dy, dx, ignore)

    def measure_intercept(
        self,
        grain_map: np.ndarray,
        step_size: tuple[float, float],
        ignore: int = -1,
    ) -> tuple[GrainSizeResult, list, np.ndarray, np.ndarray]:
        """Same as ``measure`` for the intercept method, but also returns the
        test-line geometry to DRAW — ``(result, lines, xs, ys)`` — so the
        measurement is visible and checkable on the map (Eloïse #15: "voir les
        lignes tracées et les intercepts pour pouvoir contrôler"). ``lines`` is a
        list of ``((x0, y0), (x1, y1))`` endpoint pairs, ``xs``/``ys`` the
        boundary-crossing points, all in pixel coordinates."""
        dy, dx = step_size
        return self._intercept(grain_map, dy, dx, ignore)

    @staticmethod
    def _astm_number(mean_size_um: float) -> float:
        """ASTM E112 grain-size number from a mean lineal size in micrometres.
        G = -6.6457 log10(L_mm) - 3.298 (log10, not log2 — log2 inflates G ~3.3x
        into impossible values like 37)."""
        mean_mm = max(mean_size_um / 1000.0, 1e-6)
        return -6.6457 * float(np.log10(mean_mm)) - 3.298

    def _test_lines(self, h: int, w: int) -> list[tuple[str, tuple, tuple]]:
        """Evenly-spaced horizontal + vertical test lines (the ASTM E112 grid),
        endpoints ``(x, y)`` in pixel coords centred on each row / column."""
        lines: list[tuple[str, tuple, tuple]] = []
        for y in np.unique(np.linspace(0, h - 1, self.n_lines, dtype=int)):
            lines.append(("h", (0.0, float(y) + 0.5), (float(w), float(y) + 0.5)))
        for x in np.unique(np.linspace(0, w - 1, self.n_lines, dtype=int)):
            lines.append(("v", (float(x) + 0.5, 0.0), (float(x) + 0.5, float(h))))
        return lines

    def _intercept(self, grain_map: np.ndarray, dy: float, dx: float, ignore: int):
        h, w = grain_map.shape
        total_cross = 0
        total_len = 0.0
        seg_lines: list[tuple[tuple, tuple]] = []
        all_ix: list[np.ndarray] = []
        all_iy: list[np.ndarray] = []
        for axis, p0, p1 in self._test_lines(h, w):
            ix, iy = line_intercepts(grain_map, p0, p1, ignore=ignore)
            if len(ix) == 0:
                continue
            # count length over the RECONSTRUCTED span only (skip the -1 border),
            # scaled by THIS axis's pitch — dx along a row, dy down a column
            if axis == "h":
                recon_px = int(np.sum(grain_map[int(p0[1]), :] != ignore))
                total_len += recon_px * dx
            else:
                recon_px = int(np.sum(grain_map[:, int(p0[0])] != ignore))
                total_len += recon_px * dy
            total_cross += len(ix)
            seg_lines.append((p0, p1))
            all_ix.append(ix)
            all_iy.append(iy)

        mean_int = total_len / max(total_cross, 1)
        xs = np.concatenate(all_ix) if all_ix else np.empty(0)
        ys = np.concatenate(all_iy) if all_iy else np.empty(0)
        valid = grain_map[grain_map != ignore]
        result = GrainSizeResult(
            mean_intercept_um=mean_int,
            astm_grain_size_number=self._astm_number(mean_int),
            total_crossings=total_cross,
            total_line_length_um=total_len,
            equivalent_diameter_um=0.0,
            grain_count=int(len(np.unique(valid))),
            method="intercept",
        )
        return result, seg_lines, xs, ys

    def _area(self, grain_map: np.ndarray, dy: float, dx: float, ignore: int):
        ids, counts = np.unique(grain_map, return_counts=True)
        keep = ids != ignore
        ids, counts = ids[keep], counts[keep]
        areas = counts * dx * dy  # anisotropic cell area, not step²
        eq_diams = 2 * np.sqrt(areas / np.pi)
        mean_diam = float(eq_diams.mean()) if len(eq_diams) else 0.0
        return GrainSizeResult(
            mean_intercept_um=mean_diam,
            astm_grain_size_number=self._astm_number(mean_diam),
            total_crossings=0,
            total_line_length_um=0.0,
            equivalent_diameter_um=mean_diam,
            grain_count=int(len(ids)),
            method="area",
        )
