"""app entrypoint — the --gpu-check diagnostic must report the live compute
backend/device without booting Qt, so a user can confirm GPU use."""

import sys

from pagb_reconstruction import app


def test_gpu_check_prints_backend_without_gui(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pagb-reconstruction", "--gpu-check"])
    app.main()  # returns early, never constructs a QApplication
    out = capsys.readouterr().out
    assert "compute_backend" in out
    assert "compute_device" in out
    assert "cuda_available" in out
