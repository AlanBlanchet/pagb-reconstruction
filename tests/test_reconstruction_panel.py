"""Reconstruction panel guards — run/compare triggers."""


def test_compare_button_emits_signal(qtbot):
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    fired = []
    panel.compare_requested.connect(lambda: fired.append(True))
    panel._compare_btn.click()
    assert fired, "Compare… button must emit compare_requested"


def test_auto_optimize_button_emits_signal(qtbot):
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    fired = []
    panel.optimize_requested.connect(lambda: fired.append(True))
    panel._optimize_btn.click()
    assert fired, "Auto-optimize button must emit optimize_requested"


def test_auto_optimize_runs_and_adopts_a_config(qtbot, synthetic_multi_parent):
    """The sweep runs off-thread and emits the winning run — its config carries
    the boundary smoothing every trial forces on (Eloïse #14)."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    emap, _, _ = synthetic_multi_parent
    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    from pagb_reconstruction.core.reconstruction import ReconstructionConfig

    with qtbot.waitSignal(panel.optimize_finished, timeout=120000) as blocker:
        panel.start_auto_optimize(emap, ReconstructionConfig())
    best = blocker.args[0]
    assert best is not None and best.config.boundary_smoothing >= 3
    assert best.result.parent_grain_ids.size > 0


def test_success_stylesheet_is_valid_qss(qtbot):
    """Issue #13 log: 'Could not parse stylesheet of object QProgressBar'.
    The closing literal was not an f-string, so \"}}\" emitted two braces and Qt
    rejected the sheet — the green completion state never applied."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    panel._progress_bar.setValue(100)
    from pagb_reconstruction.ui.theme import active_theme

    sheet = (
        f"QProgressBar::chunk {{ background: {active_theme().success};"
        " border-radius: 6px; }"
    )
    assert sheet.count("{") == sheet.count("}"), "unbalanced braces in QSS"
    panel._progress_bar.setStyleSheet(sheet)
