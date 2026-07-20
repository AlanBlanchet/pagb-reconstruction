"""Run several reconstruction configurations on one map and score each.

The literature's way to pick the best reconstruction is to run competing
configurations (different algorithms, ORs, or parameter values) on the same data
and judge them on shared quality metrics — grain size vs the expected material
size, OR fit angle, % reconstructed (Taylor et al. 2024 compare AZtec vs MTEX
variant-graph exactly this way; Hielscher et al. 2022 sweep the inflation
parameter). This module is the generic runner behind the Compare view.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.fit_metrics import (
    ReconstructionQuality,
    reconstruction_quality,
)
from pagb_reconstruction.core.reconstruction import (
    ReconstructionConfig,
    ReconstructionEngine,
    ReconstructionResult,
)


@dataclass(frozen=True)
class ComparisonRun:
    name: str
    config: ReconstructionConfig
    result: ReconstructionResult
    quality: ReconstructionQuality


def compare_configs(
    emap: EBSDMap,
    named_configs: list[tuple[str, ReconstructionConfig]],
    progress_callback: Callable[[str, float], None] | None = None,
) -> list[ComparisonRun]:
    """Run each named config on ``emap``; progress spans all runs 0→1 with the
    run name prefixed so the user can follow which approach is computing."""
    runs: list[ComparisonRun] = []
    n = len(named_configs)
    for i, (name, cfg) in enumerate(named_configs):

        def cb(msg: str, frac: float, _i: int = i, _name: str = name):
            if progress_callback:
                progress_callback(f"[{_name}] {msg}", (_i + frac) / n)

        result = ReconstructionEngine(emap, cfg).run(progress_callback=cb)
        runs.append(
            ComparisonRun(
                name=name,
                config=cfg,
                result=result,
                quality=reconstruction_quality(result, emap.step_size),
            )
        )
    return runs


def sweep_configs(
    base: ReconstructionConfig, field: str, values: list[float]
) -> list[tuple[str, ReconstructionConfig]]:
    """Named configs varying ONE field of ``base`` — the "vary the parameters
    for the best fit" workflow as a sweep."""
    return [(f"{field}={v:g}", base.model_copy(update={field: v})) for v in values]


def grid_configs(
    base: ReconstructionConfig, values_by_field: dict[str, list[float]]
) -> list[tuple[str, ReconstructionConfig]]:
    """Named configs for EVERY combination of the given fields.

    ``sweep_configs`` varies one field; optimising a reconstruction usually means
    trading several against each other (tolerance vs threshold), so this walks
    the full grid. Fields not listed keep their value from ``base``.
    """
    import itertools

    fields = sorted(values_by_field)
    combos = itertools.product(*(values_by_field[f] for f in fields))
    out: list[tuple[str, ReconstructionConfig]] = []
    for combo in combos:
        update = dict(zip(fields, combo))
        name = ", ".join(f"{f}={v:g}" for f, v in update.items())
        out.append((name, base.model_copy(update=update)))
    return out


def rank_runs(runs: list[ComparisonRun], metric: str = "balanced") -> list[ComparisonRun]:
    """Best-first ordering of comparison runs.

    ``fit``           lowest mean misfit angle first.
    ``reconstructed`` highest reconstructed fraction first.
    ``balanced``      both together — a run that reconstructs a sliver of the map
                      can show a beautiful fit while being useless, so fit is
                      weighted by coverage.
    """
    if metric == "fit":
        return sorted(runs, key=lambda r: r.quality.mean_fit_deg)
    if metric == "reconstructed":
        return sorted(runs, key=lambda r: -r.quality.pct_reconstructed)
    if metric != "balanced":
        raise ValueError(f"unknown metric: {metric!r}")

    def score(run: ComparisonRun) -> float:
        coverage = max(run.quality.pct_reconstructed, 1e-6) / 100.0
        # misfit per unit of map actually explained: lower is better
        return run.quality.mean_fit_deg / coverage

    return sorted(runs, key=score)


def parent_map_rgb(emap: EBSDMap, result: ReconstructionResult) -> np.ndarray:
    """IPF-Z colouring of the reconstructed parent orientations as a (rows, cols,
    3) float RGB grid; unreconstructed pixels are neutral grey (same convention
    as the Parent Grains display map)."""
    from orix.quaternion import Orientation
    from orix.vector import Vector3d

    from pagb_reconstruction.utils.colormap import ipf_colors

    rows, cols = emap.shape
    ori = Orientation(result.parent_orientations, symmetry=emap.primary_symmetry())
    rgb = ipf_colors(ori, Vector3d.zvector())
    rgb = emap._to_grid(np.clip(rgb, 0.0, 1.0))
    pids = emap._to_grid(result.parent_grain_ids.astype(np.float64), fill=-1.0)
    rgb[pids < 0] = 0.18
    return rgb
