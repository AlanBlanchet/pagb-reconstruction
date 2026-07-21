# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

datas = copy_metadata('pagb-reconstruction')
binaries = []
hidden = [
    "pagb_reconstruction",
    # compiled Rust kernels (rust/); imported lazily in utils/compute.py, so
    # PyInstaller needs telling
    "pagb_kernels",
    "networkx", "packaging",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_qtagg",
    "PySide6", "qdarktheme", "superqt",
]

# orix (lazy_loader .pyi stubs), qtawesome (icon fonts) and qtsass (_sass
# C ext) all ship runtime data/binaries PyInstaller misses without collect_all.
for pkg in ["orix", "diffpy", "qtawesome", "qtsass"]:
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

# The SCSS stylesheet is read at runtime via importlib.resources.
datas += [("src/pagb_reconstruction/ui/theme/app.scss", "pagb_reconstruction/ui/theme")]

# GPU: stage the CUDA compiler (NVVM + libdevice) and runtime into the bundle so
# numba can compile our kernels (utils/quaternion_kernels.py) on a machine that
# has only a display driver. ~61 MB — the CUDA *math* libraries a tensor library
# needs (cudnn/cublas/...) are not required, we generate our own kernels.
def _stage_cuda_payload():
    import glob
    import importlib.util
    import shutil

    found = importlib.util.find_spec("nvidia")
    if found is None or not found.submodule_search_locations:
        print("pagb: no CUDA payload staged (nvidia wheels absent) — GPU will fall back to CPU")
        return []
    root = list(found.submodule_search_locations)[0]
    stage_root = os.path.join("build", "cuda_payload")
    staged = []

    def stage(src, rel):
        dst = os.path.join(stage_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        staged.append((dst, os.path.join("cuda", os.path.dirname(rel))))

    # numba's library finder requires a VERSIONED name on Linux (libnvvm.so.N).
    for f in glob.glob(os.path.join(root, "cuda_nvcc/nvvm/lib64/libnvvm.so*")):
        stage(f, "nvvm/lib64/libnvvm.so.4")
    for f in glob.glob(os.path.join(root, "cuda_nvcc/nvvm/bin/nvvm*.dll")):
        stage(f, os.path.join("nvvm/bin", os.path.basename(f)))
    for f in glob.glob(os.path.join(root, "cuda_nvcc/nvvm/libdevice/*.bc")):
        stage(f, os.path.join("nvvm/libdevice", os.path.basename(f)))
    for f in glob.glob(os.path.join(root, "cuda_runtime/lib/libcudart.so*")):
        stage(f, os.path.join("lib64", os.path.basename(f)))
    for f in glob.glob(os.path.join(root, "cuda_runtime/bin/cudart*.dll")):
        stage(f, os.path.join("bin", os.path.basename(f)))
    print(f"pagb: staged {len(staged)} CUDA payload files")
    return staged


datas += _stage_cuda_payload()


for pkg in ["numba", "scipy", "sklearn", "h5py", "pydantic", "matplotlib", "pyqtgraph"]:
    hidden += collect_submodules(pkg)

a = Analysis(
    ["src/pagb_reconstruction/app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The GPU path is numba-compiled kernels (utils/quaternion_kernels.py), not a
    # tensor library. Excluded here so a stray torch in the build environment
    # cannot silently add gigabytes to the bundle.
    excludes=["torch", "torchgen", "functorch", "triton"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pagb-reconstruction",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="pagb-reconstruction",
)
