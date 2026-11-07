# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
# PyInstaller spec: one-folder build, windowed, no UPX (fewer antivirus false positives).
# Build:  pyinstaller --noconfirm --clean packaging/spinfix.spec
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent

hidden = (
    collect_submodules("spinfix")
    + collect_submodules("winrt")
    + ["pi_heif", "pypdfium2", "pikepdf", "send2trash", "win32com.shell.shell"]
)

a = Analysis(
    [str(root / "packaging" / "spinfix_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "assets" / "logo" / "spinfix-logo.png"), "assets/logo"),
        (str(root / "assets" / "spinfix.ico"), "assets"),
        (str(root / "LICENSE"), "."),
        (str(root / "THIRD_PARTY_NOTICES.md"), "."),
    ],
    hiddenimports=hidden,
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtMultimedia", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Spinfix",
    console=False,
    icon=str(root / "assets" / "spinfix.ico"),
    upx=False,
    version=str(root / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Spinfix")
