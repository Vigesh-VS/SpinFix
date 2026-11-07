# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Global hotkey (default Ctrl+Alt+Space) via RegisterHotKey — no keyboard hooks."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QObject, Signal

from spinfix.core.errors import get_logger

log = get_logger("hotkey")

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID = 0x5F17
KEYS = {
    "space": 0x20,
    **{chr(c).lower(): c for c in range(0x41, 0x5B)},
    **{str(d): 0x30 + d for d in range(10)},
}
MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    for part in parts[:-1]:
        if part not in MODS:
            return None
        mods |= MODS[part]
    key = KEYS.get(parts[-1])
    if key is None or not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None
    return mods, key


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, emitter: HotkeySignals) -> None:
        super().__init__()
        self.emitter = emitter

    def nativeEventFilter(  # noqa: N802 — Qt override
        self, event_type: QByteArray | bytes | bytearray | memoryview, message: int
    ) -> object:
        raw = event_type.data() if isinstance(event_type, QByteArray) else bytes(event_type)
        if raw == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.emitter.pressed.emit()
                return True, 0
        return False, 0


class HotkeySignals(QObject):
    pressed = Signal()


class Hotkey:
    def __init__(self) -> None:
        self.signals = HotkeySignals()
        self.filter = HotkeyFilter(self.signals)
        self.registered = False

    def register(self, text: str) -> bool:
        self.unregister()
        parsed = parse_hotkey(text)
        if parsed is None:
            log.warning("invalid hotkey setting")
            return False
        mods, key = parsed
        ok = bool(ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, key))
        if not ok:
            log.warning("hotkey is already used by another app")
        self.registered = ok
        return ok

    def unregister(self) -> None:
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False
