# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['windows_marker.pyw'],
    pathex=[],
    binaries=[],
    datas=[('data', 'data'), ('core', 'core'), ('.wheels', '.wheels')],
    hiddenimports=['openpyxl', 'openpyxl.cell._writer', 'et_xmlfile'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LegalMarker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
