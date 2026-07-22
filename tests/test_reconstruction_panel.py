"""Reconstruction panel guards — run/compare triggers."""


def test_compare_button_emits_signal(qtbot):
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    fired = []
    panel.compare_requested.connect(lambda: fired.append(True))
    panel._compare_btn.click()
    assert fired, "Compare… button must emit compare_requested"


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
