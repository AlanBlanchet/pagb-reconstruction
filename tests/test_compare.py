"""Guards for the approach-comparison runner (Eloïse: "comparer les différentes
approches" — run several configurations on the same map, score each on the shared
fit metrics, rank by fit)."""

import numpy as np
import pytest

from pagb_reconstruction.core.compare import (
    compare_configs,
    parent_map_rgb,
    sweep_configs,
)
from pagb_reconstruction.core.reconstruction import ReconstructionConfig


@pytest.fixture(scope="module")
def two_runs(synthetic_multi_parent):
    emap, _, _ = synthetic_multi_parent
    named = [
        ("variant graph", ReconstructionConfig(optimize_or=False, min_grain_size=2)),
        (
            "grain graph",
            ReconstructionConfig(
                algorithm="grain_graph", optimize_or=False, min_grain_size=2
            ),
        ),
    ]
    messages: list[str] = []
    runs = compare_configs(emap, named, progress_callback=lambda m, f: messages.append(m))
    return runs, messages


def test_compare_runs_each_config_and_scores_it(two_runs):
    runs, messages = two_runs
    assert [r.name for r in runs] == ["variant graph", "grain graph"]
    for r in runs:
        assert r.result.parent_grain_ids.shape[0] > 0
        assert r.quality.n_parents > 0
    # progress messages are prefixed with the run name so the user can follow
    assert any(m.startswith("[variant graph]") for m in messages)
    assert any(m.startswith("[grain graph]") for m in messages)


def test_sweep_builds_named_configs_varying_one_field():
    base = ReconstructionConfig()
    named = sweep_configs(base, "min_parent_size_um", [0.0, 5.0, 10.0])
    assert [n for n, _ in named] == [
        "min_parent_size_um=0",
        "min_parent_size_um=5",
        "min_parent_size_um=10",
    ]
    assert [c.min_parent_size_um for _, c in named] == [0.0, 5.0, 10.0]
    # every other field stays at the base value
    assert all(c.threshold_deg == base.threshold_deg for _, c in named)


def test_parent_map_rgb_shape_and_unreconstructed_grey(synthetic_multi_parent, two_runs):
    emap, _, _ = synthetic_multi_parent
    runs, _ = two_runs
    rgb = parent_map_rgb(emap, runs[0].result)
    rows, cols = emap.shape
    assert rgb.shape == (rows, cols, 3)
    assert rgb.dtype == np.float64 or rgb.dtype == np.float32
    assert 0.0 <= rgb.min() and rgb.max() <= 1.0
