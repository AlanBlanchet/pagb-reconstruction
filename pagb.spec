# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["src/pagb_reconstruction/app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pagb_reconstruction",
        "orix",
        "h5py",
        "numba",
        "scipy",
        "sklearn",
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
