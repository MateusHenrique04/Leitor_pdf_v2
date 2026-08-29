# -*- mode: python ; coding: utf-8 -*-
#
# Build: pyinstaller main.spec
# Gera dist/main.exe — NÃO commite dist/ nem build/ (ver .gitignore).
#
# `langdetect` carrega arquivos de dados (perfis de idioma) via pkgutil,
# que o PyInstaller não detecta sozinho por análise estática — sem
# collect_data_files() o .exe falha silenciosamente ao detectar idioma
# em produção mesmo funcionando normalmente com `python main.py`.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
hiddenimports = []

datas += collect_data_files("langdetect")
hiddenimports += collect_submodules("bs4")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='main',
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
