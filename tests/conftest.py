import pytest
from pathlib import Path

from pagb_reconstruction.io import load_ebsd
from pagb_reconstruction.core.reconstruction import ReconstructionConfig, ReconstructionEngine


@pytest.fixture(scope="session")
def sample_ebsd():
    return load_ebsd(Path("data/sdss_ferrite_austenite.ang"))


@pytest.fixture(scope="session")
def sample_with_grains(sample_ebsd):
    sample_ebsd.run_grain_detection(threshold_deg=5.0, min_size=5)
    return sample_ebsd


@pytest.fixture(scope="session")
def variant_graph_result(sample_ebsd):
    config = ReconstructionConfig(algorithm="variant_graph")
    engine = ReconstructionEngine(sample_ebsd, config)
    return engine.run()
