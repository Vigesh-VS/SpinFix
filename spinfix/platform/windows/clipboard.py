# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Put text or files on the Windows clipboard (files as CF_HDROP, like Explorer's Copy)."""

from __future__ import annotations

import struct
import time
from collections.abc import Sequence
from pathlib import Path

import win32clipboard
import win32con

DROPFILES_SIZE = 20  # sizeof(DROPFILES)


def _open() -> None:
    for _ in range(20):  # another app may hold the clipboard briefly
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(0.05)
    win32clipboard.OpenClipboard()


def set_text(text: str) -> None:
    _open()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def set_files(paths: Sequence[Path]) -> None:
    files = "".join(f"{p.resolve()}\0" for p in paths) + "\0"
    payload = files.encode("utf-16-le")
    # DROPFILES: pFiles offset, pt.x, pt.y, fNC, fWide
    header = struct.pack("<IiiII", DROPFILES_SIZE, 0, 0, 0, 1)
    _open()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, header + payload)
        effect = win32clipboard.RegisterClipboardFormat("Preferred DropEffect")
        win32clipboard.SetClipboardData(effect, struct.pack("<I", 1))  # DROPEFFECT_COPY
    finally:
        win32clipboard.CloseClipboard()


def get_text() -> str:
    _open()
    try:
        data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return str(data)
    finally:
        win32clipboard.CloseClipboard()
