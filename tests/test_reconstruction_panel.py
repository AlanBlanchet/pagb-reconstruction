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


def test_step_counter_counts_real_steps_not_fake_total(qtbot):
    """#16 surface: the old "Step N/13" was int(pct*13) against a 13-name union
    list no single run traverses — it collided, skipped, and mismatched the
    true step (the "Step 6/13" Eloïse quoted). The counter now increments once
    per genuinely new step, collapses the repeated "Refining OR (iter N)"
    sub-messages, and shows NO fabricated denominator."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    panel._step_index = 0  # simulate a run start
    panel._last_step_base = None

    seq = [
        ("Detecting grains", 0.0),
        ("Setting up OR", 0.15),
        ("Refining OR", 0.2),
        ("Refining OR (iter 10)", 0.21),   # sub-step -> must NOT count again
        ("Refining OR (iter 180)", 0.30),  # sub-step -> must NOT count again
        ("Building variant graph", 0.3),
        ("Computing variant edges (337179 pairs)", 0.35),  # a real distinct step
        ("Clustering variants", 0.5),
        ("Boundary-vote growth", 0.7),
        ("Merging similar", 0.8),
        ("Merging inclusions", 0.85),
        ("Removing noise islands", 0.9),
        ("Computing variants", 0.95),
        ("Done", 1.0),
    ]
    nums = []
    for msg, frac in seq:
        panel._on_progress(msg, frac)
        text = panel._step_counter.text()
        assert "/" not in text, f"no fabricated denominator, got {text!r}"
        nums.append(int(text.split()[1]))

    # 3 "Refining OR" messages collapse to ONE step -> 12 distinct steps total.
    assert nums == [1, 2, 3, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], nums
    assert panel._step_counter.text() == "Step 12"


def test_failure_line_is_highlighted_and_not_counted(qtbot):
    """An "Error:" line is shown in the log and must NOT bump the step counter
    (it is not a step) — the failure has to stand out in the log a bug report
    captures (#16 surface). The colour itself is a visual-critic check."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    panel._step_index = 0
    panel._last_step_base = None

    panel._on_progress("Clustering variants", 0.5)  # a real step -> Step 1
    assert panel._step_counter.text() == "Step 1"
    panel._on_progress("Error: Unable to allocate 256. GiB", -1.0)

    assert "Error: Unable to allocate 256. GiB" in panel._log.toPlainText()
    assert panel._step_counter.text() == "Step 1"  # the error did not advance it
    # the error line carries the semantic error colour (the pixels are a critic check)
    from pagb_reconstruction.ui.theme import active_theme

    assert active_theme().error.lower() in panel._log.document().toHtml().lower()


def test_log_lines_are_numbered_with_phase_name(qtbot):
    """A copied log line pairs the step number with its phase — a bare "Step N"
    alone is uninformative for a bug report."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    panel._step_index = 0
    panel._last_step_base = None
    for msg, frac in [("Detecting grains", 0.0), ("Setting up OR", 0.15), ("Clustering variants", 0.5)]:
        panel._on_progress(msg, frac)
    log = panel._log.toPlainText()
    assert "Step 1: Detecting grains" in log
    assert "Step 3: Clustering variants" in log


def test_progress_log_is_tall_enough_to_read_a_failure(qtbot):
    """The 60px (~2 line) log clipped the error text a bug report needs (#16)."""
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    assert panel._log.maximumHeight() > 60
    assert panel._log.isReadOnly()  # read-only QPlainTextEdit stays copyable


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
