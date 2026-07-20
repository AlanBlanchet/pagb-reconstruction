# -*- mode: python ; coding: utf-8 -*-
# Onefile spec for standalone .exe (Windows releases)
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

datas = copy_metadata('pagb-reconstruction')
binaries = []
hidden = [
    "pagb_reconstruction",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
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
