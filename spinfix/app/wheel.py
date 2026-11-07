# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""The radial wheel: a transparent, topmost, non-activating overlay.

Drag mode: Explorer keeps the drag; the wheel receives the real file paths through normal
Windows drag-and-drop. The drop is always accepted as COPY, so Explorer never deletes the
source (Shift normally means "move" in Explorer).

Click mode (hotkey, tray, right-click): files are already known; click a slice or press 1-8.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFocusEvent,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from spinfix.app import theme
from spinfix.core import filetype
from spinfix.core.errors import UserError
from spinfix.core.filetype import FileInfo
from spinfix.core.registry import Action

SIZE = 460
OUTER = 188
INNER = 64
MAX_SLICES = 8
NO_DRAG_TIMEOUT_MS = 750


@dataclass
class Page:
    title: str
    actions: list[Action]


PagesFor = Callable[[Sequence[FileInfo]], list[Page]]


def infos_from_paths(paths: Sequence[Path]) -> list[FileInfo]:
    infos: list[FileInfo] = []
    for p in paths:
        try:
            infos.append(filetype.detect(p))
        except UserError:
            continue
    return infos


class WheelWindow(QWidget):
    chosen = Signal(object, object)  # Action, list[FileInfo]
    cancelled = Signal()

    def __init__(self, pages_for: PagesFor) -> None:
        super().__init__(None)
        self.pages_for = pages_for
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(SIZE, SIZE)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.pages: list[Page] = []
        self.page_index = 0
        self.hover: int | None = None
        self.infos: list[FileInfo] = []
        self.mode = "drag"
        self.got_drag = False
        self._no_drag = QTimer(self, singleShot=True, interval=NO_DRAG_TIMEOUT_MS)
        self._no_drag.timeout.connect(self._maybe_hide_no_drag)
        self._release_grace = QTimer(self, singleShot=True, interval=400)
        self._release_grace.timeout.connect(self._cancel)

    # ------------------------------------------------------------- showing

    def _place(self, global_pos: QPoint) -> None:
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(global_pos.x() - SIZE // 2, area.left()), area.right() - SIZE)
        y = min(max(global_pos.y() - SIZE // 2, area.top()), area.bottom() - SIZE)
        self.move(x, y)

    def show_for_drag(self) -> None:
        """Called by the drag watcher when the trigger key is pressed mid-drag."""
        self.mode = "drag"
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.infos, self.pages, self.page_index, self.hover = [], [], 0, None
        self.got_drag = False
        self._place(QCursor.pos())
        self.show()
        self.raise_()
        self._no_drag.start()
        self.update()

    def show_for_files(self, paths: Sequence[Path]) -> None:
        """Click mode: the files are known (hotkey, tray, right-click)."""
        self.mode = "click"
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, False)
        self.infos = infos_from_paths(paths)
        self.pages = self.pages_for(self.infos)
        self.page_index, self.hover = 0, None
        self._place(QCursor.pos())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.update()

    def cycle(self) -> None:
        if len(self.pages) > 1:
            self.page_index = (self.page_index + 1) % len(self.pages)
            self.hover = None
            self.update()

    def drag_released(self) -> None:
        """Mouse button came up. If no drop arrives shortly, it was dropped elsewhere."""
        if self.isVisible() and self.mode == "drag":
            self._release_grace.start()

    def _maybe_hide_no_drag(self) -> None:
        if self.mode == "drag" and not self.got_drag:
            self._cancel()

    def _cancel(self) -> None:
        if self.isVisible():
            self.hide()
            self.cancelled.emit()

    def cancel(self) -> None:
        self._cancel()

    # ------------------------------------------------------------- geometry

    @property
    def current(self) -> list[Action]:
        if not self.pages:
            return []
        return self.pages[self.page_index].actions[:MAX_SLICES]

    def slice_at(self, pos: QPointF) -> int | None:
        n = len(self.current)
        if n == 0:
            return None
        dx, dy = pos.x() - SIZE / 2, pos.y() - SIZE / 2
        r = math.hypot(dx, dy)
        if r < INNER or r > OUTER + 24:
            return None
        angle = (math.degrees(math.atan2(dy, dx)) + 90 + 360) % 360  # 0 = top, clockwise
        span = 360 / n
        return int(((angle + span / 2) % 360) // span)

    # ------------------------------------------------------------- drag & drop

    @staticmethod
    def _local_paths(event: QDropEvent | QDragEnterEvent | QDragMoveEvent) -> list[Path]:
        data = event.mimeData()
        if not data.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in data.urls() if u.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 — Qt override
        paths = self._local_paths(event)
        if not paths:
            event.ignore()
            return
        self.got_drag = True
        self._no_drag.stop()
        self._release_grace.stop()
        if not self.infos:
            self.infos = infos_from_paths(paths)
            self.pages = self.pages_for(self.infos)
            self.page_index = 0
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.update()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        self._release_grace.stop()
        hover = self.slice_at(event.position())
        if hover != self.hover:
            self.hover = hover
            self.update()
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event: object) -> None:  # noqa: N802
        self.hover = None
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        # COPY, never MOVE: Explorer must keep the original where it is.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        index = self.slice_at(event.position())
        paths = self._local_paths(event)
        infos = infos_from_paths(paths) if paths else self.infos
        self._finish(index, infos)

    def _finish(self, index: int | None, infos: list[FileInfo]) -> None:
        actions = self.current
        self.hide()
        self._release_grace.stop()
        if index is None or index >= len(actions) or not infos:
            self.cancelled.emit()
            return
        self.chosen.emit(actions[index], infos)

    # ------------------------------------------------------------- click mode

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        hover = self.slice_at(event.position())
        if hover != self.hover:
            self.hover = hover
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.mode != "click":
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.cycle()
            return
        self._finish(self.slice_at(event.position()), self.infos)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._cancel()
        elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Shift, Qt.Key.Key_Space, Qt.Key.Key_Right):
            self.cycle()
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_8:
            index = key - Qt.Key.Key_1
            if index < len(self.current):
                self._finish(int(index), self.infos)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        if self.mode == "click":
            QTimer.singleShot(0, self._cancel)
        super().focusOutEvent(event)

    # ------------------------------------------------------------- painting

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        # Almost-invisible fill so the whole square catches drops (alpha 0 is click-through).
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        c = QPointF(SIZE / 2, SIZE / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.GLASS)
        p.drawEllipse(c, OUTER + 8, OUTER + 8)

        actions = self.current
        n = len(actions)
        if n:
            span = 360 / n
            gap = 1.6 if n > 1 else 0
            for i, action in enumerate(actions):
                start = -90 - span / 2 + i * span + gap / 2
                path = self._segment(c, start, span - gap)
                hovered = i == self.hover
                unavailable = action.needs is not None and action.available() is not None
                fill = theme.ORANGE if hovered else theme.SLICE
                p.setBrush(fill)
                p.setPen(QPen(theme.GLASS_EDGE, 1))
                p.drawPath(path)
                mid = math.radians(start + (span - gap) / 2)
                rr = (OUTER + INNER) / 2 - 2
                tx, ty = c.x() + rr * math.cos(mid), c.y() + rr * math.sin(mid)
                box = QRectF(tx - 46, ty - 24, 92, 48)
                p.setPen(theme.TEXT_DIM if unavailable and not hovered else theme.TEXT)
                p.setFont(theme.font(9.5, bold=True))
                p.drawText(
                    box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, action.title
                )
                if self.mode == "click":
                    nr = OUTER - 8
                    nx, ny = c.x() + nr * math.cos(mid), c.y() + nr * math.sin(mid)
                    p.setFont(theme.font(7.5))
                    p.setPen(theme.TEXT_DIM)
                    p.drawText(
                        QRectF(nx - 8, ny - 8, 16, 16), Qt.AlignmentFlag.AlignCenter, str(i + 1)
                    )

        # Centre: wheel name, page dots, hint.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(10, 10, 12, 245))
        p.drawEllipse(c, INNER - 6, INNER - 6)
        p.setPen(QPen(theme.ORANGE, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(
            QRectF(c.x() - INNER + 6, c.y() - INNER + 6, 2 * INNER - 12, 2 * INNER - 12),
            30 * 16,
            60 * 16,
        )
        p.setPen(theme.TEXT)
        p.setFont(theme.font(11, bold=True))
        if self.pages:
            title = self.pages[self.page_index].title
            hint = "Shift: next" if self.mode == "drag" else "Tab: next"
        elif self.mode == "drag" and not self.got_drag:
            title, hint = "Spinfix", "Move to a slice"
        else:
            title, hint = "Nothing fits", "Esc to close"
        p.drawText(QRectF(c.x() - 56, c.y() - 22, 112, 24), Qt.AlignmentFlag.AlignCenter, title)
        p.setFont(theme.font(7.5))
        p.setPen(theme.TEXT_DIM)
        if len(self.pages) > 1:
            p.drawText(QRectF(c.x() - 56, c.y() + 2, 112, 16), Qt.AlignmentFlag.AlignCenter, hint)
            dots = len(self.pages)
            for i in range(dots):
                x = c.x() + (i - (dots - 1) / 2) * 10
                p.setBrush(theme.ORANGE if i == self.page_index else theme.TEXT_DIM)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(x, c.y() + 26), 2.6, 2.6)
        else:
            p.drawText(
                QRectF(c.x() - 56, c.y() + 4, 112, 16),
                Qt.AlignmentFlag.AlignCenter,
                "Esc to cancel" if self.pages else hint,
            )
        p.end()

    @staticmethod
    def _segment(c: QPointF, start_deg: float, sweep_deg: float) -> QPainterPath:
        outer = QRectF(c.x() - OUTER, c.y() - OUTER, 2 * OUTER, 2 * OUTER)
        inner = QRectF(c.x() - INNER, c.y() - INNER, 2 * INNER, 2 * INNER)
        path = QPainterPath()
        # Qt angles are counter-clockwise from 3 o'clock; ours are clockwise.
        path.arcMoveTo(outer, -start_deg)
        path.arcTo(outer, -start_deg, -sweep_deg)
        path.arcTo(inner, -(start_deg + sweep_deg), sweep_deg)
        path.closeSubpath()
        return path
