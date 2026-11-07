# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Small toast in the corner: progress, result line, Open / Show in folder / Undo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QEnterEvent, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spinfix.app import theme
from spinfix.core.jobs import JobResult, JobState
from spinfix.core.safe_io import human_size
from spinfix.platform.windows import shell

AUTO_HIDE_MS = 7000


def result_line(result: JobResult) -> str:
    if result.state is not JobState.DONE:
        return result.message
    if result.clipboard_text is not None:
        preview = " ".join(result.clipboard_text.split())[:90]
        return f"Copied: {preview}" + ("…" if len(result.clipboard_text) > 90 else "")
    if result.clipboard_files:
        return "Copied to the clipboard."
    files = [p for p in result.outputs if p.is_file()]
    if result.input_bytes and files and len(result.outputs) == len(files):
        before, after = result.input_bytes, result.output_bytes
        line = f"{human_size(before)} → {human_size(after)}"
        if after < before:
            line += f" · {round(100 * (1 - after / before))} % smaller"
        return line
    if len(result.outputs) == 1:
        return f"Saved {result.outputs[0].name}"
    return f"Saved {len(result.outputs)} items"


class Toast(QFrame):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self.outputs: list[Path] = []
        self.on_cancel: Callable[[], None] | None = None

        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(20,20,24,240); border: 1px solid #3A3A44;"
            " border-radius: 12px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            theme.logo_pixmap().scaled(
                22,
                22,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not theme.logo_pixmap().isNull()
            else QPixmap()
        )
        top.addWidget(icon)
        self.title = QLabel()
        self.title.setFont(theme.font(10, bold=True))
        top.addWidget(self.title, 1)
        close = QPushButton("✕")
        close.setFixedSize(24, 24)
        close.setStyleSheet("QPushButton { border: none; background: transparent; }")
        close.clicked.connect(self.hide)
        top.addWidget(close)
        lay.addLayout(top)

        self.line = QLabel()
        self.line.setWordWrap(True)
        self.line.setStyleSheet("color: #D8D4CC;")
        lay.addWidget(self.line)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)

        buttons = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.folder_btn = QPushButton("Show in folder")
        self.undo_btn = QPushButton("Undo")
        self.cancel_btn = QPushButton("Cancel")
        for b in (self.open_btn, self.folder_btn, self.undo_btn, self.cancel_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        self.open_btn.clicked.connect(self._open)
        self.folder_btn.clicked.connect(self._folder)
        self.undo_btn.clicked.connect(self._undo)
        self.cancel_btn.clicked.connect(self._cancel)

        self._hide_timer = QTimer(self, singleShot=True, interval=AUTO_HIDE_MS)
        self._hide_timer.timeout.connect(self.hide)

    # ------------------------------------------------------------- states

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.adjustSize()
        self.move(QPoint(area.right() - self.width() - 16, area.bottom() - self.height() - 16))

    def _buttons(self, running: bool, outputs: bool) -> None:
        self.cancel_btn.setVisible(running)
        for b in (self.open_btn, self.folder_btn, self.undo_btn):
            b.setVisible(outputs and not running)

    def started(self, title: str, on_cancel: Callable[[], None]) -> None:
        self._hide_timer.stop()
        self.on_cancel = on_cancel
        self.outputs = []
        self.title.setText(title)
        self.line.setText("Starting…")
        self.bar.setValue(0)
        self.bar.show()
        self._buttons(running=True, outputs=False)
        self._place()
        self.show()
        self.raise_()

    def progress(self, fraction: float, message: str) -> None:
        self.bar.setValue(int(fraction * 1000))
        if message:
            self.line.setText(message)

    def finished(self, title: str, result: JobResult) -> None:
        self.on_cancel = None
        self.outputs = [p for p in result.outputs if p.exists()]
        ok = result.state is JobState.DONE
        self.title.setText(title if ok else f"{title} — not done")
        text = result_line(result)
        if result.notes:
            text += "\n" + "\n".join(result.notes[:3])
        self.line.setText(text)
        self.bar.hide()
        self._buttons(running=False, outputs=ok and bool(self.outputs))
        self._place()
        self.show()
        self.raise_()
        self._hide_timer.start(AUTO_HIDE_MS * (2 if not ok or result.notes else 1))

    def message(self, title: str, text: str) -> None:
        self.title.setText(title)
        self.line.setText(text)
        self.bar.hide()
        self._buttons(running=False, outputs=False)
        self._place()
        self.show()
        self._hide_timer.start(AUTO_HIDE_MS)

    # ------------------------------------------------------------- buttons

    def _open(self) -> None:
        if self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.outputs[0])))
        self.hide()

    def _folder(self) -> None:
        shell.show_in_folder(self.outputs)
        self.hide()

    def _undo(self) -> None:
        count = shell.recycle(self.outputs)
        self.outputs = []
        self.message("Undone", f"Moved {count} item{'s' if count != 1 else ''} to the Recycle Bin.")

    def _cancel(self) -> None:
        if self.on_cancel:
            self.on_cancel()
        self.line.setText("Cancelling…")

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802 — Qt override
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        if self.on_cancel is None and self.isVisible():
            self._hide_timer.start(3000)


def make_toast() -> QWidget:
    return Toast()
