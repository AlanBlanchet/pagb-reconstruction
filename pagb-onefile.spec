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

# orix uses lazy_loader with .pyi stubs — need collect_all to get data files
for pkg in ["orix", "diffpy"]:
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

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
    excludes=[],
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
