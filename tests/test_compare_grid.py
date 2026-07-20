"""Issue #10: 'plusieurs jeux de paramètres, tolerance, threshold... et que je
puisse choisir le meilleur' — vary SEVERAL parameters together and rank the runs.
sweep_configs only ever varied one field."""

from pagb_reconstruction.core.compare import (
    ComparisonRun,
    grid_configs,
    rank_runs,
)
from pagb_reconstruction.core.fit_metrics import ReconstructionQuality
from pagb_reconstruction.core.reconstruction import ReconstructionConfig


def test_grid_covers_every_combination():
    base = ReconstructionConfig()
    grid = grid_configs(base, {"tolerance_deg": [2.0, 3.0], "merge_similar_deg": [5.0, 7.0]})
    assert len(grid) == 4
    combos = {
        (c.tolerance_deg, c.merge_similar_deg) for _, c in grid
    }
    assert combos == {(2.0, 5.0), (2.0, 7.0), (3.0, 5.0), (3.0, 7.0)}
    # names identify which set produced which row
    assert all("tolerance_deg=" in n and "merge_similar_deg=" in n for n, _ in grid)


def test_grid_leaves_untouched_fields_alone():
    base = ReconstructionConfig(min_cluster_size=3)
    for _, cfg in grid_configs(base, {"tolerance_deg": [2.0, 4.0]}):
        assert cfg.min_cluster_size == 3


def _run(name, fit, recon):
    q = ReconstructionQuality(
        n_parents=10, pct_reconstructed=recon, mean_fit_deg=fit,
        median_fit_deg=fit, fit_q25_deg=fit, fit_q75_deg=fit, fit_q95_deg=fit,
        area_weighted_ecd_um=20.0, mean_ecd_um=20.0, median_ecd_um=20.0,
    )
    return ComparisonRun(name=name, config=ReconstructionConfig(), result=None, quality=q)


def test_rank_by_fit_then_recon():
    runs = [_run("a", 5.0, 90.0), _run("b", 3.0, 88.0), _run("c", 9.0, 99.0)]
    assert [r.name for r in rank_runs(runs, metric="fit")] == ["b", "a", "c"]
    assert [r.name for r in rank_runs(runs, metric="reconstructed")] == ["c", "a", "b"]


def test_balanced_rank_trades_fit_against_coverage():
    # a run that reconstructs almost nothing must not win on fit alone
    runs = [_run("thorough", 6.0, 95.0), _run("sliver", 1.0, 12.0)]
    assert rank_runs(runs, metric="balanced")[0].name == "thorough"
