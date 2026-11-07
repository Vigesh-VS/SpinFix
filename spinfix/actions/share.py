# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Share actions: copy path, copy file to clipboard."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from spinfix.core.filetype import Category, FileInfo
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel


class CopyPath(Action):
    id = "share.copy_path"
    title = "Copy path"
    icon = "link"
    wheel = Wheel.SHARE
    order = 10
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        paths = [str(i.path.resolve()) for i in inputs]
        quoted = options.get("quoted", len(paths) > 1)
        ctx.clipboard_text = "\n".join(f'"{p}"' if quoted else p for p in paths)
        return []


class CopyFile(Action):
    id = "share.copy_file"
    title = "Copy file"
    icon = "copy"
    wheel = Wheel.SHARE
    order = 20
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        ctx.clipboard_files = [i.path.resolve() for i in inputs]
        return []


def register(registry: Registry) -> None:
    registry.register(CopyPath())
    registry.register(CopyFile())
