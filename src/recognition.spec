# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['recognition.py'],
    pathex=[],  # Aquí puedes añadir el path donde está tu script si no está en el directorio actual
    binaries=[],
    datas=[('settings.config', '.')],  # Incluir settings.config en el directorio raíz del ejecutable
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name='recognition',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Cambia a False si no deseas que se muestre la consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
