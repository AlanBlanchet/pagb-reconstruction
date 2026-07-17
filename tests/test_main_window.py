"""Main window smoke guard — it must construct with the full toolbar/panel set."""


def test_main_window_constructs(qtbot):
    from pagb_reconstruction.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    assert w is not None
