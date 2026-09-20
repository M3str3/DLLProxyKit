# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT / "src"))

datas = [
    (
        str(ROOT / "src" / "dllproxykit" / "langs"),
        "dllproxykit/langs",
    ),
    (
        str(ROOT / "src" / "dllproxykit" / "tcc.zip"),
        "dllproxykit",
    ),
]

a = Analysis(
    [str(ROOT / "src" / "dllproxykit" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("dllproxykit"),
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
    name="DLLProxyKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
