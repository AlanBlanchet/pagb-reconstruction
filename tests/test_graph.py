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

from pagb_reconstruction.core.graph import _grain_connected_components


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
