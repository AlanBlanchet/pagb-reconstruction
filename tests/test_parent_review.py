"""The parent-review panel: surface incoherent parents and reattach them."""

import numpy as np

from pagb_reconstruction.core.reconstruction import ReconstructionResult


def _result():
    pids = np.array([0, 0, 0, 0, 1, 1, 1, 2], dtype=np.int32)
    fits = np.array([0.5, 0.4, 0.6, 0.5, 9.0, 8.0, 10.0, 2.0])
    quats = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (pids.size, 1))
    quats[pids == 1] = [0.0, 1.0, 0.0, 0.0]
    z = np.zeros(pids.size, dtype=np.int32)
    return ReconstructionResult(
        parent_orientations=quats, parent_grain_ids=pids, fit_angles=fits,
        variant_ids=z, packet_ids=z, block_ids=z, bain_ids=z,
    )


def test_panel_lists_worst_fit_first(qtbot):
    from pagb_reconstruction.ui.widgets.parent_review import ParentReviewPanel

    panel = ParentReviewPanel()
    qtbot.addWidget(panel)
    panel.set_result(_result())
    assert panel._table.rowCount() == 3
    # worst misfit is the top row — what she should inspect first
    assert panel._table.item(0, 0).text() == "1"


def test_selecting_a_row_emits_the_parent_id(qtbot):
    from pagb_reconstruction.ui.widgets.parent_review import ParentReviewPanel

    panel = ParentReviewPanel()
    qtbot.addWidget(panel)
    panel.set_result(_result())
    with qtbot.waitSignal(panel.parent_selected) as blocker:
        panel._table.selectRow(0)
    assert blocker.args == [1]


def test_reassign_emits_source_and_target(qtbot):
    from pagb_reconstruction.ui.widgets.parent_review import ParentReviewPanel

    panel = ParentReviewPanel()
    qtbot.addWidget(panel)
    panel.set_result(_result())
    panel._table.selectRow(0)          # parent 1 (worst)
    panel._target_spin.setValue(0)
    with qtbot.waitSignal(panel.reassign_requested) as blocker:
        panel._reassign_btn.click()
    assert blocker.args == [1, 0]


def test_no_result_leaves_panel_empty(qtbot):
    from pagb_reconstruction.ui.widgets.parent_review import ParentReviewPanel

    panel = ParentReviewPanel()
    qtbot.addWidget(panel)
    assert panel._table.rowCount() == 0
    assert not panel._reassign_btn.isEnabled()
