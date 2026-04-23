# -*- mode: python ; coding: utf-8 -*-
# Onefile spec for standalone .exe (Windows releases)
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata('pagb-reconstruction')

a = Analysis(
    ["src/pagb_reconstruction/app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pagb_reconstruction",
        "orix",
        "orix.quaternion.symmetry",
        "h5py",
        "numba",
        "scipy",
        "sklearn",
        "networkx",
        "pydantic",
        "packaging",
        "matplotlib",
        "matplotlib.backends.backend_agg",
        "matplotlib.backends.backend_qtagg",
        "PySide6",
        "pyqtgraph",
        "qdarktheme",
        "superqt",
    ],
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
