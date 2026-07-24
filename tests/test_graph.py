"""Variant-graph clustering guards.

Focus: the no-attractor fallback. When MCL fails to form attractors (a sparse
variant graph — e.g. an OR that does not perfectly match the data), the cluster
step must NOT return every grain as its own parent (``np.arange``), which renders
as reconstruction "dust". It must instead group grains that are connected in the
variant graph via connected components, so a real (if coarse) parent structure
survives. This is the mechanism behind the "only dust appears" bug report.
"""

import numpy as np
from scipy import sparse

from pagb_reconstruction.core.graph import _grain_connected_components, variant_graph_cluster


def test_variant_cluster_never_densifies(monkeypatch):
    """The attractor branch must not build a grains x clusters DENSE matrix.

    Regression for issue #16 ("problème taille"): on a full-resolution map MCL
    formed ~182681 clusters over ~188445 grains, and the vote step allocated a
    (188445, 182681) float64 array = 256 GiB -> MemoryError, so reconstruction
    FAILED at "Clustering variants". Grain->cluster assignment is a grouped
    argmax and needs no dense grid.

    Machine-independent: rather than rely on RAM, forbid ANY 2-D dense
    ``np.zeros`` inside the clustering step. The legit call there is 1-D
    (``cluster_labels``); only the dense vote matrix is 2-D.
    """
    from pagb_reconstruction.core import graph

    n_grains, n_variants = 120, 2
    dim = n_grains * n_variants
    # Block-diagonal: each grain's variant nodes interlink, grains disjoint. MCL
    # then yields ~one attractor per grain -> n_clusters == n_grains, the exact
    # near-square regime that produced the 256 GiB matrix.
    rows, cols = [], []
    for g in range(n_grains):
        a, b = g * n_variants, g * n_variants + 1
        rows += [a, b]
        cols += [b, a]
    adj = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(dim, dim))
    all_candidates = np.zeros((n_grains, n_variants, 4))
    all_candidates[..., 0] = 1.0  # unit quats; the value is irrelevant here

    real_zeros = np.zeros

    def guarded_zeros(shape, *a, **k):
        if isinstance(shape, tuple) and len(shape) >= 2 and all(s > 1 for s in shape[:2]):
            raise MemoryError(f"issue #16: refused dense 2-D allocation {shape}")
        return real_zeros(shape, *a, **k)

    monkeypatch.setattr(graph.np, "zeros", guarded_zeros)

    _, _, cluster_labels = variant_graph_cluster(
        adj, all_candidates, n_grains, n_variants, inflation=1.1
    )
    assert cluster_labels.shape == (n_grains,)
    # Disconnected grains -> each is its own parent; done without a dense grid.
    assert len(np.unique(cluster_labels)) == n_grains


def test_connected_components_group_linked_grains():
    # 3 grains, 2 variants each (dim=6). Edges link grain0<->grain1 (via some
    # variant nodes); grain2 is isolated.
    n_grains, n_variants = 3, 2
    dim = n_grains * n_variants
    rows = [0, 2]  # node 0 (grain0,v0) <-> node 2 (grain1,v0)
    cols = [2, 0]
    adj = sparse.csr_matrix(
        (np.ones(len(rows)), (rows, cols)), shape=(dim, dim)
    )
    labels = _grain_connected_components(adj, n_grains, n_variants)

    assert labels.shape == (n_grains,)
    # grain0 and grain1 share a component; grain2 is separate.
    assert labels[0] == labels[1]
    assert labels[2] != labels[0]


def test_connected_components_not_all_isolated():
    # A chain 0-1-2 must collapse to ONE parent, never three (the dust signature).
    n_grains, n_variants = 3, 2
    dim = n_grains * n_variants
    # grain0(node0) - grain1(node2) - grain2(node4)
    rows = [0, 2, 2, 4]
    cols = [2, 0, 4, 2]
    adj = sparse.csr_matrix(
        (np.ones(len(rows)), (rows, cols)), shape=(dim, dim)
    )
    labels = _grain_connected_components(adj, n_grains, n_variants)
    assert len(np.unique(labels)) == 1, "connected chain must be one parent, not dust"


def _vote_grain(gid, quat, neighbors):
    import numpy as np

    from pagb_reconstruction.core.grain import Grain

    return Grain(
        id=gid,
        pixel_indices=np.arange(4),
        mean_quaternion=np.asarray(quat, dtype=np.float64),
        phase_id=0,
        area=4,
        pixel_rc=np.zeros((4, 2), dtype=int),
        neighbor_ids=list(neighbors),
    )


def _gb_vote_setup():
    """Three assigned grains around two unassigned ones.

    Grain 3's orientation IS a KS variant of parent 0's orientation, so its fit
    is ~0 and it must be adopted. Grain 4 is far from every variant of every
    neighbouring parent, so no matter how many neighbours vote, the fit gate
    must reject it.
    """
    import numpy as np

    from pagb_reconstruction.core.orientation_relationship import (
        OrientationRelationship,
    )
    from pagb_reconstruction.core.phase import PhaseConfig

    or_ = OrientationRelationship.from_preset(
        "KS", PhaseConfig.austenite(), PhaseConfig.ferrite()
    )
    parent_quats = np.array([[1.0, 0.0, 0.0, 0.0]])
    variants = or_.variant_quaternions()

    child_ok = variants[3]  # exactly a variant of parent 0
    rng = np.random.default_rng(5)
    q = rng.normal(size=4)
    child_bad = q / np.linalg.norm(q)  # unrelated orientation

    grains = [
        _vote_grain(1, child_ok, [4, 2]),
        _vote_grain(2, child_ok, [1, 4, 5]),
        _vote_grain(3, child_ok, [4]),
        _vote_grain(4, child_ok, [1, 2, 3, 5]),   # unassigned, compatible
        _vote_grain(5, child_bad, [2, 4]),        # unassigned, incompatible
    ]
    labels = np.array([0, 0, 0, -1, -1])
    return grains, labels, parent_quats, or_


def test_gb_vote_fill_adopts_compatible_neighbour():
    import numpy as np

    from pagb_reconstruction.core.graph import gb_vote_fill

    grains, labels, parent_quats, or_ = _gb_vote_setup()
    sym = np.asarray(
        or_.parent_phase.symmetry.data, dtype=np.float64
    ).reshape(-1, 4)
    out = gb_vote_fill(
        labels, grains, parent_quats, or_, sym,
        threshold_deg=3.5, iterations=8, min_prob=0.5,
    )
    assert out[3] == 0, "compatible grain must be adopted by its neighbours' parent"
    assert out[4] == -1, "incompatible grain must stay unassigned despite neighbours"
    # already-assigned labels are never rewritten
    assert list(out[:3]) == [0, 0, 0]


def test_gb_vote_fill_min_prob_gate():
    """A grain whose assigned neighbours split across parents below min_prob
    stays unassigned."""
    import numpy as np

    from pagb_reconstruction.core.graph import gb_vote_fill

    grains, labels, parent_quats, or_ = _gb_vote_setup()
    sym = np.asarray(
        or_.parent_phase.symmetry.data, dtype=np.float64
    ).reshape(-1, 4)
    out = gb_vote_fill(
        labels, grains, parent_quats, or_, sym,
        threshold_deg=3.5, iterations=8, min_prob=1.01,  # impossible bar
    )
    assert out[3] == -1
