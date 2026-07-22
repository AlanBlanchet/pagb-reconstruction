import numpy as np
import pytest
from pathlib import Path

from pagb_reconstruction.io import ANGLoader, CTFLoader, HDF5Loader, load_ebsd
from pagb_reconstruction.io.reconstruction_export import ReconstructionExporter


def test_loaders_cover_expected_formats():
    from pagb_reconstruction.io import CRCLoader

    exts = {
        e
        for L in (ANGLoader, CTFLoader, HDF5Loader, CRCLoader)
        for e in L.supported_extensions
    }
    assert {".ang", ".ctf", ".h5", ".crc"} <= exts


def test_ang_preserves_phase_names_and_per_phase_lattice():
    """orix autogenerates phase names ('Austenite' -> 'Fe-432-A') and, as a side
    effect, collapses every phase's lattice to the last phase read — so austenite
    loaded at a=2.87 instead of its real 3.595. Both must survive the load, or the
    IPF legend and phase map mislabel the microstructure."""
    m = load_ebsd(Path("data/sdss_ferrite_austenite.ang"))
    by_name = {p.name.lower(): p for p in m.phases}
    assert "austenite" in by_name, f"austenite name lost: {[p.name for p in m.phases]}"
    assert "ferrite" in by_name
    assert by_name["austenite"].lattice.a == pytest.approx(3.595, abs=0.01), (
        f"austenite lattice collapsed to {by_name['austenite'].lattice.a}"
    )
    assert by_name["ferrite"].lattice.a == pytest.approx(2.867, abs=0.01)


def test_crc_loader_roundtrip(tmp_path):
    # A tiny Channel5 .crc + .cpr (no large fixture needed): 25-byte records,
    # phase byte + 3 Bunge Euler floats, rest skipped.
    (tmp_path / "t.cpr").write_text(
        "[Job]\nxCells=2\nyCells=2\nGridDistX=0.5\nGridDistY=0.5\n"
        "[Phases]\n[Phase1]\nStructureName=Iron bcc\nLaueGroup=11\n"
    )
    rec = np.dtype([("phase", "u1"), ("euler", "<f4", (3,)), ("rest", "V", 12)])
    arr = np.zeros(4, dtype=rec)
    arr["phase"] = 1
    arr["euler"] = [[0, 0, 0], [0.1, 0.2, 0.3], [1.0, 0.5, 1.0], [2.0, 1.0, 2.0]]
    (tmp_path / "t.crc").write_bytes(arr.tobytes())

    m = load_ebsd(tmp_path / "t.crc")
    assert m.shape == (2, 2)
    assert "iron" in m.phase_name(1).lower()


def test_martensite_ctf_loads():
    m = load_ebsd(Path("data/martensite_roomtemp.ctf"))
    assert m.shape == (501, 667)
    assert any("iron" in p.name.lower() for p in m.phases)


def test_hdf5_roundtrip(sample_ebsd, tmp_path):
    out = tmp_path / "roundtrip.h5"
    HDF5Loader().save(sample_ebsd, out)
    reloaded = load_ebsd(out)
    assert reloaded.shape == sample_ebsd.shape
    assert len(reloaded.phases) == len(sample_ebsd.phases)


def test_phase_lookup_by_id_not_index(sample_ebsd):
    # Phase ids here are 1-based, so indexing the phase list by id is wrong.
    assert sample_ebsd.phase_name(1) == "austenite"
    assert sample_ebsd.phase_name(2) == "ferrite"
    # Guard the off-by-index bug: list[1] is ferrite, not the id-1 phase.
    assert sample_ebsd.phases[1].name != sample_ebsd.phase_name(1)


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
