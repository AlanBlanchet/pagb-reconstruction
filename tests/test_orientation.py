"""Cold-import guards: utils submodules must import standalone, without the
utils<->core colormap cycle."""

import subprocess
import sys


def _cold_import(module: str):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stderr


def test_orientation_imports_standalone():
    rc, err = _cold_import("pagb_reconstruction.core.orientation")
    assert rc == 0, err


def test_compute_imports_standalone():
    rc, err = _cold_import("pagb_reconstruction.utils.compute")
    assert rc == 0, err
