"""Cold-import guards: utils submodules must import without the utils<->core
colormap cycle. The GPU bootstrap (compute.py importing gpu_runtime, and the
--gpu-check diagnostic) depends on gpu_runtime importing standalone."""

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


def test_gpu_runtime_imports_standalone():
    rc, err = _cold_import("pagb_reconstruction.utils.gpu_runtime")
    assert rc == 0, err


def test_compute_imports_standalone():
    rc, err = _cold_import("pagb_reconstruction.utils.compute")
    assert rc == 0, err
