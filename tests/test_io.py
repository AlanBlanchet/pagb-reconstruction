import pytest
from pathlib import Path

from pagb_reconstruction.io import load_ebsd


def test_load_ang(sample_ebsd):
    assert sample_ebsd.shape == (100, 117)
    assert len(sample_ebsd.phases) == 2


def test_phase_names(sample_ebsd):
    names = {p.name.lower() for p in sample_ebsd.phases}
    assert "austenite" in names
    assert "ferrite" in names


def test_bad_path_raises():
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        load_ebsd(Path("nonexistent_file.ang"))
