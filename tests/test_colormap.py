"""colormap must stay core-free at import so the utils<->core cycle can't form.
core.phase is used only as a type annotation (guarded by TYPE_CHECKING)."""

import subprocess
import sys

import numpy as np


def test_colormap_imports_standalone():
    result = subprocess.run(
        [sys.executable, "-c", "import pagb_reconstruction.utils.colormap"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_colormap_module_does_not_import_core_phase_at_runtime():
    # After import, core.phase must NOT have been dragged in transitively by
    # colormap alone — proving the runtime edge into core is gone.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pagb_reconstruction.utils.colormap as c; "
            "assert 'pagb_reconstruction.core.phase' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_phase_colormap_returns_rgb():
    from pagb_reconstruction.core.phase import PhaseConfig
    from pagb_reconstruction.utils.colormap import phase_colormap

    ids = np.array([0, 0, 1, 1])
    rgb = phase_colormap(ids, [PhaseConfig.austenite(), PhaseConfig.ferrite()])
    assert rgb.shape[0] == ids.size
    assert rgb.shape[-1] in (3, 4)
