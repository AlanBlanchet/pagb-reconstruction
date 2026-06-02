import numpy as np
import pytest
from pathlib import Path

from pagb_reconstruction.io import load_ebsd
from pagb_reconstruction.io.reconstruction_export import ReconstructionExporter


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


def test_export_unsupported_suffix_raises(sample_ebsd, variant_graph_result, tmp_path):
    with pytest.raises(ValueError, match="Unsupported export format"):
        ReconstructionExporter.save(
            tmp_path / "out.xyz", sample_ebsd, variant_graph_result
        )


@pytest.mark.parametrize("suffix", [".npz", ".ang"])
def test_export_roundtrip(sample_ebsd, variant_graph_result, tmp_path, suffix):
    out = tmp_path / f"recon{suffix}"
    ReconstructionExporter.save(out, sample_ebsd, variant_graph_result)
    assert out.exists() and out.stat().st_size > 0

    if suffix == ".ang":
        # An exported .ang re-loads with the same grid and phase set.
        reloaded = load_ebsd(out)
        assert reloaded.shape == sample_ebsd.shape
        assert len(reloaded.phases) == len(sample_ebsd.phases)
    else:
        archive = np.load(out)
        assert tuple(archive["shape"]) == sample_ebsd.shape
        n = int(np.prod(sample_ebsd.shape))
        assert archive["parent_grain_ids"].shape[0] == n
        assert archive["parent_orientations"].shape == (n, 4)
