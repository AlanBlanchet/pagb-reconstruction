"""Reconstruction quality / fit metrics.

The literature judges a parent-grain reconstruction's "closeness to reality" by
a small set of complementary numbers, not one:
  * fit angle — disorientation of each child grain from its cluster's parent OR
    (Niessen et al. 2022; the variant-graph vote residual). Lower = better fit.
  * % reconstructed — fraction of pixels assigned a parent (Hielscher et al. 2022).
  * parent grain size — area-weighted equivalent circle diameter, the headline
    number metallurgists check against the material (Taylor et al. 2024); real
    prior-austenite grains are ~15–50 µm.

This module computes them generically from a ReconstructionResult so any approach
can be scored and — in future — different approaches compared on equal footing.
"""

from dataclasses import dataclass

import numpy as np

from pagb_reconstruction.core.reconstruction import ReconstructionResult


@dataclass(frozen=True)
class ReconstructionQuality:
    n_parents: int
    pct_reconstructed: float
    mean_fit_deg: float
    median_fit_deg: float
    fit_q25_deg: float
    fit_q75_deg: float
    fit_q95_deg: float
    area_weighted_ecd_um: float
    mean_ecd_um: float
    median_ecd_um: float


def reconstruction_quality(
    result: ReconstructionResult, step_size_um: tuple[float, float]
) -> ReconstructionQuality:
    """Score a reconstruction. ``step_size_um`` is (dy, dx) in µm."""
    pids = result.parent_grain_ids
    labelled = pids[pids >= 0]
    n_parents = int(np.unique(labelled).size)
    pct = 100.0 * labelled.size / pids.size if pids.size else 0.0

    fit = result.fit_angles[~np.isnan(result.fit_angles)]
    if fit.size:
        mean_fit = float(np.mean(fit))
        median_fit = float(np.median(fit))
        q25, q75, q95 = (float(x) for x in np.percentile(fit, [25, 75, 95]))
    else:
        mean_fit = median_fit = q25 = q75 = q95 = 0.0

    dy_um, dx_um = step_size_um
    px_area = dx_um * dy_um
    if labelled.size:
        areas_um2 = np.bincount(labelled) * px_area
        areas_um2 = areas_um2[areas_um2 > 0]
        ecd = np.sqrt(4.0 * areas_um2 / np.pi)
        # Area-weighted ECD: large grains dominate, robust to many noise islands.
        area_wtd = float(np.sum(areas_um2 * ecd) / np.sum(areas_um2))
        mean_ecd = float(np.mean(ecd))
        median_ecd = float(np.median(ecd))
    else:
        area_wtd = mean_ecd = median_ecd = 0.0

    return ReconstructionQuality(
        n_parents=n_parents,
        pct_reconstructed=pct,
        mean_fit_deg=mean_fit,
        median_fit_deg=median_fit,
        fit_q25_deg=q25,
        fit_q75_deg=q75,
        fit_q95_deg=q95,
        area_weighted_ecd_um=area_wtd,
        mean_ecd_um=mean_ecd,
        median_ecd_um=median_ecd,
    )
