"""Slip-system geometry invariants.

A slip direction must lie IN its slip plane (n . d = 0). Two BCC systems
violated this, which let the Schmid factor exceed its physical maximum of 0.5.
"""

import numpy as np

from pagb_reconstruction.core.constants import SlipSystems


def _pairs():
    s = SlipSystems()
    return (
        ("bcc", s.bcc_planes, s.bcc_dirs),
        ("fcc", s.fcc_planes, s.fcc_dirs),
    )


def test_slip_direction_lies_in_slip_plane():
    for family, planes, dirs in _pairs():
        assert len(planes) == len(dirs), f"{family}: plane/direction count mismatch"
        for i, (n, d) in enumerate(zip(planes, dirs)):
            assert abs(float(np.dot(n, d))) < 1e-12, (
                f"{family} system {i}: direction {d.astype(int)} is not in plane "
                f"{n.astype(int)} (n.d={np.dot(n, d):+.0f})"
            )


def test_schmid_factor_cannot_exceed_one_half():
    """With n perpendicular to d, max(cos_phi * cos_lam) = 0.5. Sample many
    orientations; any value above 0.5 means the geometry is wrong."""
    rng = np.random.default_rng(0)
    q = rng.normal(size=(4000, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    rz = np.stack(
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], axis=1
    )
    for family, planes, dirs in _pairs():
        un = planes / np.linalg.norm(planes, axis=1, keepdims=True)
        ud = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
        sf = (np.abs(rz @ un.T) * np.abs(rz @ ud.T)).max(axis=1)
        assert sf.max() <= 0.5 + 1e-9, f"{family}: Schmid factor {sf.max():.4f} > 0.5"


def test_slip_family_from_phase_name():
    """BCC and FCC are BOTH m-3m (48 operations), so crystal symmetry cannot
    choose the slip family — the phase identity must. Selecting by symmetry size
    silently gave every cubic phase the FCC systems."""
    from pagb_reconstruction.core.constants import slip_family

    for name in ("Iron fcc", "Austenite", "gamma-Fe", "FCC"):
        assert slip_family(name) == "fcc", name
    for name in ("Iron bcc (old)", "Ferrite", "Martensite", "alpha-Fe", "BCC"):
        assert slip_family(name) == "bcc", name
    # steel default when the name says nothing
    assert slip_family("") == "bcc"
    assert slip_family(None) == "bcc"
