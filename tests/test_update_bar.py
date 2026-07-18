"""Update bar guards — the download progress must be legible so the user knows
whether an update is running / finished."""


def test_progress_shows_percent_text(qtbot):
    from pagb_reconstruction.ui.widgets.update_bar import UpdateBar

    bar = UpdateBar()
    qtbot.addWidget(bar)
    # percentage text must be visible so a slow download reads as progressing.
    assert bar._progress.isTextVisible()


def test_show_update_labels_version_and_hides_progress(qtbot):
    from pagb_reconstruction.ui.widgets.update_bar import UpdateBar

    bar = UpdateBar()
    qtbot.addWidget(bar)
    bar.show_update("9.9.9", "https://example.com/rel", "https://example.com/app.exe")
    assert "9.9.9" in bar._label.text()
    assert bar.isVisible()
    assert not bar._progress.isVisible()  # only shown once downloading


def test_set_progress_updates_bar(qtbot):
    from pagb_reconstruction.ui.widgets.update_bar import UpdateBar

    bar = UpdateBar()
    qtbot.addWidget(bar)
    bar._progress.setVisible(True)
    bar._progress.setValue(42)
    assert bar._progress.value() == 42
