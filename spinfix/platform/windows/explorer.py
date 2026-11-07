# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Read the files selected in the active File Explorer window or on the Desktop (Shell COM)."""

from __future__ import annotations

import contextlib
import ctypes
from pathlib import Path

from spinfix.core.errors import get_logger

log = get_logger("explorer")

SWC_DESKTOP = 8
SWFO_NEEDDISPATCH = 1
CSIDL_DESKTOP = 0


def _foreground_root() -> int:
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    user32.GetAncestor.restype = ctypes.c_void_p
    hwnd = user32.GetForegroundWindow()
    return int(user32.GetAncestor(hwnd, 2) or hwnd or 0)


def _foreground_class() -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(ctypes.c_void_p(_foreground_root()), buf, 256)
    return buf.value


def _paths_from_view(document: object) -> list[Path]:
    items = document.SelectedItems()  # type: ignore[attr-defined]
    paths: list[Path] = []
    for i in range(items.Count):
        path = str(items.Item(i).Path)
        # Real file system paths only (skip virtual items like "::{GUID}").
        if path[1:3] == ":\\" or path.startswith("\\\\"):
            p = Path(path)
            if p.exists():
                paths.append(p)
    return paths


def selected_files() -> list[Path]:
    """Selected items in the foreground Explorer window (or Desktop). Empty if none."""
    try:
        import pythoncom  # noqa: PLC0415 — Windows only
        import win32com.client  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return []
    pythoncom.CoInitialize()
    try:
        hwnd = _foreground_root()
        cls = _foreground_class()
        shell = win32com.client.Dispatch("Shell.Application")
        if cls in ("CabinetWClass", "ExploreWClass"):
            for window in shell.Windows():
                with contextlib.suppress(Exception):
                    if int(window.HWND) == hwnd:
                        return _paths_from_view(window.Document)
        if cls in ("Progman", "WorkerW"):
            with contextlib.suppress(Exception):
                windows = shell.Windows()
                desktop = windows.FindWindowSW(
                    CSIDL_DESKTOP, None, SWC_DESKTOP, 0, SWFO_NEEDDISPATCH
                )
                if isinstance(desktop, tuple):
                    desktop = desktop[0]
                return _paths_from_view(desktop.Document)
    except Exception:
        log.exception("couldn't read the Explorer selection")
    finally:
        pythoncom.CoUninitialize()
    return []
