# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Action registry and the `Action` base class.

An action is a small class: it says which files it accepts and turns inputs into outputs.
Actions never write next to the original themselves; they write into `ctx.temp_dir` and call
`ctx.save(...)`, which commits atomically with a unique name.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from spinfix.core import safe_io
from spinfix.core.errors import CancelledError, UserError
from spinfix.core.filetype import Category, FileInfo, Kind
from spinfix.core.limits import DEFAULT_LIMITS, Limits


class Wheel(StrEnum):
    CONVERT = "convert"
    EDIT = "edit"
    TOOLS = "tools"
    SMART = "smart"
    SHARE = "share"


WHEEL_ORDER: tuple[Wheel, ...] = (Wheel.CONVERT, Wheel.EDIT, Wheel.TOOLS, Wheel.SMART, Wheel.SHARE)
WHEEL_TITLES: dict[Wheel, str] = {
    Wheel.CONVERT: "Convert",
    Wheel.EDIT: "Edit",
    Wheel.TOOLS: "Tools",
    Wheel.SMART: "Smart",
    Wheel.SHARE: "Share",
}

ProgressFn = Callable[[float, str], None]
Options = dict[str, Any]


def _no_progress(_fraction: float, _message: str) -> None:
    return None


@dataclass
class JobContext:
    """What an action gets while it runs."""

    temp_dir: Path
    limits: Limits = DEFAULT_LIMITS
    progress_fn: ProgressFn = _no_progress
    cancel_event: threading.Event = field(default_factory=threading.Event)
    output_subfolder: str | None = None
    outputs: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    clipboard_text: str | None = None
    clipboard_files: list[Path] = field(default_factory=list)

    def progress(self, fraction: float, message: str = "") -> None:
        self.check_cancel()
        self.progress_fn(max(0.0, min(1.0, fraction)), message)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise CancelledError()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def temp_file(self, name: str) -> Path:
        return self.temp_dir / safe_io.sanitize_name(name)

    def output_dir_for(self, source: Path) -> Path:
        directory = source.parent
        if self.output_subfolder:
            directory = directory / safe_io.sanitize_name(self.output_subfolder)
            if directory.is_symlink() or directory.is_junction():
                raise UserError("Spinfix won't write through a link.")
            directory.mkdir(exist_ok=True)
        return directory

    def save(self, produced: Path, source: Path, filename: str) -> Path:
        """Commit a finished temp file next to `source` (unique name, atomic)."""
        self.check_cancel()
        final = safe_io.commit_file(produced, self.output_dir_for(source), filename, self.limits)
        self.outputs.append(final)
        return final


class Action(ABC):
    """Base class for every slice on the wheel."""

    id: ClassVar[str]
    title: ClassVar[str]
    icon: ClassVar[str] = "file"
    wheel: ClassVar[Wheel] = Wheel.CONVERT
    order: ClassVar[int] = 100
    kinds: ClassVar[frozenset[Kind]] = frozenset()
    categories: ClassVar[frozenset[Category]] = frozenset()
    min_files: ClassVar[int] = 1
    max_files: ClassVar[int | None] = None
    needs: ClassVar[str | None] = None  # e.g. "ffmpeg"
    interactive: ClassVar[bool] = False  # opens a window (editors); app only
    asks: ClassVar[str | None] = None  # option the UI must ask for: target_size, size, pages

    def accepts_file(self, info: FileInfo) -> bool:
        return info.kind in self.kinds or info.category in self.categories

    def accepts(self, files: Sequence[FileInfo]) -> bool:
        if len(files) < self.min_files:
            return False
        if self.max_files is not None and len(files) > self.max_files:
            return False
        return all(self.accepts_file(f) for f in files)

    def available(self) -> str | None:
        """None when the action can run, else a friendly reason (e.g. a missing tool)."""
        return None

    @abstractmethod
    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        """Do the work. Returns the committed output paths."""


class Registry:
    def __init__(self) -> None:
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> Action:
        if action.id in self._actions:
            raise ValueError(f"duplicate action id {action.id!r}")
        self._actions[action.id] = action
        return action

    def get(self, action_id: str) -> Action:
        try:
            return self._actions[action_id]
        except KeyError:
            raise UserError(f"There's no action called {action_id!r}.") from None

    def all(self) -> list[Action]:
        return sorted(self._actions.values(), key=lambda a: (WHEEL_ORDER.index(a.wheel), a.order))

    def for_files(self, files: Sequence[FileInfo], wheel: Wheel | None = None) -> list[Action]:
        return [
            a
            for a in self.all()
            if (wheel is None or a.wheel == wheel) and files and a.accepts(files)
        ]

    def wheels_for(self, files: Sequence[FileInfo]) -> list[Wheel]:
        present = {a.wheel for a in self.for_files(files)}
        return [w for w in WHEEL_ORDER if w in present]

    def __len__(self) -> int:
        return len(self._actions)

    def __iter__(self) -> Iterator[Action]:
        return iter(self.all())
