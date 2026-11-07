# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Small shell helpers: user SID, Show in folder, Recycle Bin, start with Windows.

Registry writes are limited to HKCU and happen only when the user turns a setting on.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Sequence
from pathlib import Path

from spinfix.core.errors import get_logger

log = get_logger("shell")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Spinfix"


def user_sid() -> str:
    """The current user's SID, used to make the IPC pipe name per-user."""
    try:
        import win32api  # noqa: PLC0415
        import win32security  # noqa: PLC0415

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32security.TOKEN_QUERY
        )
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return str(win32security.ConvertSidToStringSid(sid))
    except Exception:  # pragma: no cover
        import getpass  # noqa: PLC0415

        return getpass.getuser()


def show_in_folder(paths: Sequence[Path]) -> None:
    """Open Explorer with the files selected (no command line involved)."""
    if not paths:
        return
    try:
        from win32com.shell import shell  # noqa: PLC0415

        folder = paths[0].parent
        folder_pidl = shell.SHILCreateFromPath(str(folder), 0)[0]
        items = [shell.SHILCreateFromPath(str(p), 0)[0] for p in paths if p.parent == folder]
        shell.SHOpenFolderAndSelectItems(folder_pidl, items, 0)
    except Exception:
        log.exception("show in folder failed")
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        from PySide6.QtGui import QDesktopServices  # noqa: PLC0415

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[0].parent)))


def recycle(paths: Sequence[Path]) -> int:
    """Send files/folders to the Recycle Bin. Returns how many were recycled."""
    from send2trash import send2trash  # noqa: PLC0415

    count = 0
    for p in paths:
        if p.exists():
            try:
                send2trash(str(p))
                count += 1
            except OSError:
                log.warning("couldn't recycle an output")
    return count


def launch_command() -> list[str]:
    """How Windows should start Spinfix (frozen exe or `pythonw -m spinfix`)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else exe), "-m", "spinfix"]


def _quote(parts: Sequence[str]) -> str:
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def set_start_with_windows(enabled: bool) -> None:
    """Add/remove the HKCU Run entry. Only called when the user changes the setting."""
    import winreg  # noqa: PLC0415

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(
                key, APP_NAME, 0, winreg.REG_SZ, _quote([*launch_command(), "--background"])
            )
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, APP_NAME)


def starts_with_windows() -> bool:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False
