"""Reconstruction panel guards — run/compare triggers."""


def test_compare_button_emits_signal(qtbot):
    from pagb_reconstruction.ui.widgets.reconstruction_panel import ReconstructionPanel

    panel = ReconstructionPanel()
    qtbot.addWidget(panel)
    fired = []
    panel.compare_requested.connect(lambda: fired.append(True))
    panel._compare_btn.click()
    assert fired, "Compare… button must emit compare_requested"
