# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""App controller: drag watcher → wheel → job → toast."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from spinfix.app.dialogs import ask_options
from spinfix.app.toast import Toast
from spinfix.app.wheel import MAX_SLICES, Page, WheelWindow
from spinfix.core import filetype
from spinfix.core.errors import UserError, get_logger
from spinfix.core.filetype import FileInfo
from spinfix.core.jobs import Job, JobState
from spinfix.core.limits import DEFAULT_LIMITS
from spinfix.core.registry import WHEEL_TITLES, Action, Options, Registry
from spinfix.core.settings import store
from spinfix.platform.windows.drag_watcher import DragTracker, Phase, WinInput

log = get_logger("controller")

POLL_MS = 15


def build_pages(registry: Registry, infos: Sequence[FileInfo]) -> list[Page]:
    pages: list[Page] = []
    for wheel in registry.wheels_for(infos):
        actions = registry.for_files(infos, wheel)
        chunks = [actions[i : i + MAX_SLICES] for i in range(0, len(actions), MAX_SLICES)]
        for n, chunk in enumerate(chunks):
            title = WHEEL_TITLES[wheel] + (f" {n + 1}" if n else "")
            pages.append(Page(title, chunk))
    return pages


class Controller(QObject):
    job_progress = Signal(object, float, str)  # job, fraction, message
    job_done = Signal(object)  # job

    def __init__(self, registry: Registry) -> None:
        super().__init__()
        self.registry = registry
        self.wheel = WheelWindow(lambda infos: build_pages(registry, infos))
        self.wheel.chosen.connect(self.on_chosen)
        self.wheel.cancelled.connect(self._wheel_closed)
        self.toast = Toast()
        self.queue: deque[Job] = deque()
        self.current: Job | None = None
        self.job_progress.connect(self._on_progress)
        self.job_done.connect(self._on_done)

        self.input = WinInput(store.get().trigger_key)
        dx, dy = self.input.drag_distance()
        self.tracker = DragTracker(
            on_show=lambda _x, _y: self.wheel.show_for_drag(),
            on_cycle=self.wheel.cycle,
            on_release=self.wheel.drag_released,
            on_cancel=self.wheel.cancel,
            drag_dx=dx,
            drag_dy=dy,
        )
        self._prev_button = False
        self.timer = QTimer(self, interval=POLL_MS)
        self.timer.timeout.connect(self._poll)

    # ------------------------------------------------------------- watcher

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _poll(self) -> None:
        if store.get().paused:
            return
        try:
            reading = self.input.read(need_source=self.tracker.phase is Phase.IDLE)
        except OSError:
            return
        if self.wheel.isVisible() and self.wheel.mode == "click":
            # The wheel may not get keyboard focus, so watch Esc / outside clicks here too.
            pressed = reading.button and not self._prev_button
            outside = not self.wheel.geometry().contains(QCursor.pos())
            if reading.escape or (pressed and outside):
                self.wheel.cancel()
        self._prev_button = reading.button
        self.tracker.feed(reading)

    def apply_settings(self) -> None:
        self.input.set_trigger(store.get().trigger_key)

    def _wheel_closed(self) -> None:
        self.tracker.reset()

    # ------------------------------------------------------------- entry points

    def open_files(self, paths: Sequence[Path]) -> None:
        """Hotkey, tray, right-click, Send To: show the wheel in click mode."""
        paths = [p for p in paths if p.exists()]
        if not paths:
            self.toast.message("Spinfix", "Select some files first.")
            return
        self.wheel.show_for_files(paths)

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(None, "Spinfix — pick files")
        if files:
            QTimer.singleShot(50, lambda: self.open_files([Path(f) for f in files]))

    def hotkey_pressed(self) -> None:
        from spinfix.platform.windows.explorer import selected_files  # noqa: PLC0415

        self.open_files(selected_files())

    # ------------------------------------------------------------- jobs

    def on_chosen(self, action: Action, infos: list[FileInfo]) -> None:
        self.tracker.reset()
        checked: list[FileInfo] = []
        refused: list[str] = []
        for info in infos:
            try:
                checked.append(filetype.check(info.path))
            except UserError as exc:
                refused.append(exc.message)
        if refused and not checked:
            self.toast.message(action.title, refused[0])
            return
        if action.interactive:
            self._open_editor(action, checked[0])
            return
        if len(checked) > DEFAULT_LIMITS.batch_confirm_above:
            answer = QMessageBox.question(
                None, "Spinfix", f"That's {len(checked)} files. Go ahead with {action.title}?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        options = ask_options(action, len(checked))
        if options is None:
            return
        self._add_defaults(action, options)
        settings = store.get()
        job = Job(action, checked, options, output_subfolder=settings.output_subfolder())
        if refused:
            log.info("refused %d mismatched files", len(refused))
        self.queue.append(job)
        self._next()

    def _open_editor(self, action: Action, info: FileInfo) -> None:
        edit = getattr(action, "edit", None)
        if edit is None:
            return
        try:
            save = edit(info)
        except UserError as exc:
            self.toast.message(action.title, exc.message)
            return
        if save is not None:
            self.queue.append(
                Job(save, [info], {}, output_subfolder=store.get().output_subfolder())
            )
            self._next()

    @staticmethod
    def _add_defaults(action: Action, options: Options) -> None:
        settings = store.get()
        if action.id.startswith("image.to_"):
            options.setdefault("quality", settings.jpeg_quality)
            options.setdefault("keep_metadata", settings.keep_metadata_on_convert)
        if action.id in ("image.compress",) or action.id.startswith("image.under_"):
            options.setdefault("keep_metadata", settings.keep_metadata_on_compress)
        if action.id in ("pdf.to_jpg", "pdf.to_png"):
            options.setdefault("dpi", settings.pdf_dpi)

    def _next(self) -> None:
        if self.current is not None or not self.queue:
            return
        job = self.current = self.queue.popleft()
        self.toast.started(job.action.title, job.cancel)  # always: it has the Cancel button
        job.start(
            on_progress=lambda f, m: self.job_progress.emit(job, f, m),
            on_done=self.job_done.emit,
        )

    def _on_progress(self, job: Job, fraction: float, message: str) -> None:
        if job is self.current:
            self.toast.progress(fraction, message)

    def _on_done(self, job: Job) -> None:
        result = job.result
        self.current = None
        if result is not None:
            if result.state is JobState.DONE:
                self._clipboard(result.clipboard_text, result.clipboard_files)
            quiet = not store.get().show_toasts and result.state is JobState.DONE
            if quiet and not result.notes:
                self.toast.hide()
            else:
                self.toast.finished(job.action.title, result)
        self._next()

    @staticmethod
    def _clipboard(text: str | None, files: Sequence[Path]) -> None:
        clip = QApplication.clipboard()
        if text is not None:
            clip.setText(text)
        elif files:
            data = QMimeData()
            data.setUrls([QUrl.fromLocalFile(str(p)) for p in files])
            clip.setMimeData(data)

    def shutdown(self) -> None:
        self.stop()
        for job in [self.current, *self.queue]:
            if job is not None:
                job.cancel()
