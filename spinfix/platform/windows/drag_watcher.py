# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Notice "a file drag from Explorer + trigger key" by polling mouse/key state.

Windows doesn't announce drags to other apps, so every ~15 ms we *read* three things with
GetAsyncKeyState: the left mouse button, the trigger key and Esc. That only reads state —
it can't see typing, records nothing and needs no admin rights or hooks.

The state machine is pure Python (`DragTracker`) so it can be unit-tested; `WinInput`
supplies the real readings.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
TRIGGER_VK = {"shift": VK_SHIFT, "ctrl": VK_CONTROL, "alt": VK_MENU}

SM_CXDRAG = 68
SM_CYDRAG = 69
SM_SWAPBUTTON = 23
GA_ROOT = 2

# Windows that hold files a user can drag: File Explorer and the Desktop.
SOURCE_CLASSES = frozenset({"CabinetWClass", "ExploreWClass", "Progman", "WorkerW"})


@dataclass(frozen=True, slots=True)
class Reading:
    button: bool
    trigger: bool
    escape: bool
    x: int
    y: int
    source_window: bool  # only checked when the button goes down


class Phase(Enum):
    IDLE = auto()
    PRESSED = auto()  # button down on Explorer/Desktop, not moved far yet
    DRAGGING = auto()  # moved past the drag distance with the button held
    WHEEL = auto()  # wheel is showing
    COOLDOWN = auto()  # cancelled: wait for the button to come up


class DragTracker:
    """Pure state machine. Feed it readings; it calls back on events."""

    def __init__(
        self,
        on_show: Callable[[int, int], None],
        on_cycle: Callable[[], None],
        on_release: Callable[[], None],
        on_cancel: Callable[[], None],
        drag_dx: int = 4,
        drag_dy: int = 4,
    ) -> None:
        self.on_show = on_show
        self.on_cycle = on_cycle
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.drag_dx = drag_dx
        self.drag_dy = drag_dy
        self.phase = Phase.IDLE
        self._start = (0, 0)
        self._prev_trigger = False
        self._prev_button = False

    def reset(self) -> None:
        self.phase = Phase.COOLDOWN if self._prev_button else Phase.IDLE

    def feed(self, r: Reading) -> None:
        trigger_edge = r.trigger and not self._prev_trigger
        button_edge = r.button and not self._prev_button
        self._prev_trigger = r.trigger
        self._prev_button = r.button

        if self.phase is Phase.IDLE:
            if button_edge and r.source_window:
                self.phase = Phase.PRESSED
                self._start = (r.x, r.y)
        elif self.phase is Phase.PRESSED:
            if not r.button:
                self.phase = Phase.IDLE
            elif (
                abs(r.x - self._start[0]) > self.drag_dx or abs(r.y - self._start[1]) > self.drag_dy
            ):
                self.phase = Phase.DRAGGING
                if r.trigger and trigger_edge:
                    self._show(r)
        elif self.phase is Phase.DRAGGING:
            if not r.button:
                self.phase = Phase.IDLE
            elif trigger_edge:
                self._show(r)
        elif self.phase is Phase.WHEEL:
            if r.escape:
                self.phase = Phase.COOLDOWN
                self.on_cancel()
            elif not r.button:
                self.phase = Phase.IDLE
                self.on_release()
            elif trigger_edge:
                self.on_cycle()
        elif self.phase is Phase.COOLDOWN and not r.button:
            self.phase = Phase.IDLE

    def _show(self, r: Reading) -> None:
        self.phase = Phase.WHEEL
        self.on_show(r.x, r.y)


class _POINT(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class WinInput:
    """Reads mouse and key state on Windows (read-only, no hooks)."""

    def __init__(self, trigger: str = "shift") -> None:
        if os.name != "nt":  # pragma: no cover
            raise OSError("Windows only")
        self.user32 = ctypes.windll.user32
        self.user32.WindowFromPoint.argtypes = (_POINT,)
        self.user32.WindowFromPoint.restype = ctypes.c_void_p
        self.user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        self.user32.GetAncestor.restype = ctypes.c_void_p
        self.user32.GetClassNameW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
        self.set_trigger(trigger)

    def set_trigger(self, trigger: str) -> None:
        self.trigger_vk = TRIGGER_VK.get(trigger, VK_SHIFT)

    def drag_distance(self) -> tuple[int, int]:
        return (
            int(self.user32.GetSystemMetrics(SM_CXDRAG)),
            int(self.user32.GetSystemMetrics(SM_CYDRAG)),
        )

    def _down(self, vk: int) -> bool:
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def _primary_button(self) -> int:
        return VK_RBUTTON if self.user32.GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON

    def window_class_at(self, x: int, y: int) -> str:
        hwnd = self.user32.WindowFromPoint(_POINT(x, y))
        if not hwnd:
            return ""
        root = self.user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(root, buf, 256)
        return buf.value

    def read(self, need_source: bool) -> Reading:
        pt = _POINT()
        self.user32.GetCursorPos(ctypes.byref(pt))
        button = self._down(self._primary_button())
        source = need_source and button and self.window_class_at(pt.x, pt.y) in SOURCE_CLASSES
        return Reading(
            button=button,
            trigger=self._down(self.trigger_vk),
            escape=self._down(VK_ESCAPE),
            x=pt.x,
            y=pt.y,
            source_window=source,
        )
