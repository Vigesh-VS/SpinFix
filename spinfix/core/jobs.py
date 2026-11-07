# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Jobs: run an action on a worker thread with progress, cancel and a timeout."""

from __future__ import annotations

import itertools
import shutil
import threading
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from spinfix.core import safe_io
from spinfix.core.errors import CancelledError, UserError, get_logger, short_path, user_message
from spinfix.core.filetype import FileInfo
from spinfix.core.limits import DEFAULT_LIMITS, Limits
from spinfix.core.registry import Action, JobContext, Options

log = get_logger("jobs")
_ids = itertools.count(1)


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobResult:
    state: JobState
    outputs: list[Path] = field(default_factory=list)
    message: str = ""
    notes: list[str] = field(default_factory=list)
    clipboard_text: str | None = None
    clipboard_files: list[Path] = field(default_factory=list)
    input_bytes: int = 0
    output_bytes: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.state is JobState.DONE


ProgressCallback = Callable[[float, str], None]
DoneCallback = Callable[["Job"], None]


@dataclass
class Job:
    action: Action
    inputs: Sequence[FileInfo]
    options: Options = field(default_factory=dict)
    limits: Limits = DEFAULT_LIMITS
    output_subfolder: str | None = None
    id: int = field(default_factory=lambda: next(_ids))
    state: JobState = JobState.PENDING
    result: JobResult | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel

    def run(self, on_progress: ProgressCallback | None = None) -> JobResult:
        """Run synchronously (used by the CLI and the worker thread)."""
        self.state = JobState.RUNNING
        started = time.monotonic()
        input_bytes = sum(i.size for i in self.inputs)
        ext = ",".join(sorted({i.extension or "-" for i in self.inputs}))
        log.info(
            "job %d start action=%s files=%d ext=%s bytes=%d",
            self.id,
            self.action.id,
            len(self.inputs),
            ext,
            input_bytes,
        )
        timer = threading.Timer(self.limits.job_timeout_seconds, self._cancel.set)
        timer.daemon = True
        timer.start()
        ctx: JobContext | None = None
        try:
            reason = self.action.available()
            if reason:
                raise UserError(reason)
            with safe_io.job_temp_dir() as tmp:
                ctx = JobContext(
                    temp_dir=tmp,
                    limits=self.limits,
                    progress_fn=on_progress or (lambda _f, _m: None),
                    cancel_event=self._cancel,
                    output_subfolder=self.output_subfolder,
                )
                ctx.progress(0.0, "Starting…")
                outputs = self.action.run(self.inputs, self.options, ctx)
                ctx.progress(1.0, "Done")
            result = JobResult(
                JobState.DONE,
                outputs=list(outputs),
                notes=list(ctx.notes),
                clipboard_text=ctx.clipboard_text,
                clipboard_files=list(ctx.clipboard_files),
            )
        except CancelledError as exc:
            timed_out = time.monotonic() - started >= self.limits.job_timeout_seconds
            msg = "This took too long, so Spinfix stopped it." if timed_out else exc.message
            result = JobResult(JobState.CANCELLED, message=msg)
            self._undo_partial(ctx)
        except UserError as exc:
            result = JobResult(JobState.FAILED, message=exc.message)
            self._undo_partial(ctx)
        except Exception as exc:
            log.error(
                "job %d crashed: %s\n%s",
                self.id,
                type(exc).__name__,
                "".join(traceback.format_exception(exc)),
            )
            result = JobResult(JobState.FAILED, message=user_message(exc))
            self._undo_partial(ctx)
        finally:
            timer.cancel()
        result.input_bytes = input_bytes
        result.output_bytes = sum(p.stat().st_size for p in result.outputs if p.exists())
        result.seconds = time.monotonic() - started
        self.state = result.state
        self.result = result
        log.info(
            "job %d %s outputs=%d bytes=%d in %.2fs",
            self.id,
            result.state,
            len(result.outputs),
            result.output_bytes,
            result.seconds,
        )
        return result

    def _undo_partial(self, ctx: JobContext | None) -> None:
        """A failed or cancelled job leaves nothing half-done behind."""
        if ctx is None:
            return
        for path in ctx.outputs:
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)  # a folder this job created itself
                else:
                    path.unlink()
            except OSError:
                log.warning("couldn't remove partial output %s", short_path(path))

    def start(
        self,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
    ) -> threading.Thread:
        """Run on a background thread. Callbacks are called on that thread."""

        def worker() -> None:
            self.run(on_progress)
            if on_done is not None:
                on_done(self)

        self._thread = threading.Thread(target=worker, name=f"spinfix-job-{self.id}", daemon=True)
        self._thread.start()
        return self._thread

    def wait(self, timeout: float | None = None) -> JobResult | None:
        if self._thread is not None:
            self._thread.join(timeout)
        return self.result
