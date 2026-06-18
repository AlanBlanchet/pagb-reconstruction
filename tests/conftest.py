import numpy as np
import pytest
from pathlib import Path

from orix.crystal_map import CrystalMap, Phase, PhaseList
from orix.quaternion import Orientation, Rotation

from pagb_reconstruction.io import load_ebsd
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.phase import PhaseConfig
from pagb_reconstruction.core.orientation_relationship import OrientationRelationship
from pagb_reconstruction.core.reconstruction import ReconstructionConfig, ReconstructionEngine


@pytest.fixture(scope="session")
def sample_ebsd():
    return load_ebsd(Path("data/sdss_ferrite_austenite.ang"))


@pytest.fixture(scope="session")
def synthetic_multi_parent():
    """A map with THREE known parents, each occupying a region whose child
    grains are different KS variants of that parent (child = variant * parent).

    Strong ground truth: a correct engine must recover exactly three parents,
    merge each region's variants into one parent, and match each known
    orientation — failing both the 'scramble' and 'collapse' failure modes.
    Returns (ebsd_map, region_per_pixel, parent_quaternions[3]).
    """
    ks = OrientationRelationship.kurdjumov_sachs()
    variants = ks.variant_quaternions()

    parents = np.array(
        [[0.85, 0.25, 0.35, 0.30], [0.60, -0.50, 0.40, 0.48], [0.20, 0.70, -0.55, 0.40]]
    )
    parents /= np.linalg.norm(parents, axis=1, keepdims=True)

    ny, nx = 30, 36
    yy, xx = np.mgrid[0:ny, 0:nx]
    row, col = yy.ravel(), xx.ravel()
    region = np.minimum(col // (nx // 3), 2)
    vidx = np.minimum((row // (ny // 2)) * 3 + (col % (nx // 3)) // (nx // 9), 5)

    quats = np.array(
        [
            (
                Orientation(variants[vidx[i]].reshape(1, 4))
                * Orientation(parents[region[i]].reshape(1, 4))
            ).data.flatten()
            for i in range(row.size)
        ]
    )
    xmap = CrystalMap(
        rotations=Rotation(quats),
        phase_id=np.zeros(row.size, dtype=int),
        x=col.astype(float),
        y=row.astype(float),
        phase_list=PhaseList(Phase(name="ferrite", point_group="m-3m")),
    )
    emap = EBSDMap(crystal_map=xmap, phases=[PhaseConfig.austenite()])
    return emap, region, parents


@pytest.fixture(scope="session")
def sample_with_grains(sample_ebsd):
    sample_ebsd.run_grain_detection(threshold_deg=5.0, min_size=5)
    return sample_ebsd


@pytest.fixture(scope="session")
def variant_graph_result(sample_ebsd):
    config = ReconstructionConfig(algorithm="variant_graph")
    engine = ReconstructionEngine(sample_ebsd, config)
    return engine.run()
