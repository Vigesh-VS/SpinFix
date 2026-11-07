# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Helpers shared by actions: batch loops, option parsing, output folders."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from spinfix.core import safe_io
from spinfix.core.errors import CancelledError, UserError, get_logger, short_path, user_message
from spinfix.core.filetype import FileInfo
from spinfix.core.registry import JobContext, Options

log = get_logger("actions")


def for_each(
    inputs: Sequence[FileInfo],
    ctx: JobContext,
    work: Callable[[FileInfo, Callable[[float], None]], list[Path]],
    verb: str = "Working on",
) -> list[Path]:
    """Run `work` for every input. In a batch one bad file doesn't stop the others."""
    outputs: list[Path] = []
    failures: list[str] = []
    total = len(inputs)
    for i, info in enumerate(inputs):

        def sub(fraction: float, i: int = i) -> None:
            ctx.progress((i + max(0.0, min(1.0, fraction))) / total)

        ctx.progress(i / total, f"{verb} {info.path.name} ({i + 1}/{total})")
        try:
            outputs.extend(work(info, sub))
        except CancelledError:
            raise
        except UserError as exc:
            if total == 1:
                raise
            failures.append(f"{info.path.name}: {exc.message}")
        except Exception as exc:
            if total == 1:
                raise
            log.exception("batch item failed (%s)", short_path(info.path))
            failures.append(f"{info.path.name}: {user_message(exc)}")
    if failures:
        ctx.notes.append(f"{len(failures)} of {total} files were skipped.")
        ctx.notes.extend(failures[:5])
        if not outputs:
            raise UserError(failures[0])
    return outputs


def opt_int(options: Options, key: str, default: int, lo: int, hi: int) -> int:
    value: Any = options.get(key, default)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise UserError(f"{key} must be a whole number.") from None
    if not lo <= number <= hi:
        raise UserError(f"{key} must be between {lo} and {hi}.")
    return number


def opt_str(options: Options, key: str, default: str, allowed: Sequence[str]) -> str:
    value = str(options.get(key, default)).lower()
    if value not in allowed:
        raise UserError(f"{key} must be one of: {', '.join(allowed)}.")
    return value


def parse_size(text: str) -> int:
    """'200kb' / '1.5 MB' / '500000' → bytes."""
    t = text.strip().lower().replace(" ", "")
    units = {"kb": 1024, "k": 1024, "mb": 1024 * 1024, "m": 1024 * 1024, "b": 1, "": 1}
    for unit in ("kb", "mb", "k", "m", "b", ""):
        if t.endswith(unit):
            number = t[: len(t) - len(unit)] if unit else t
            try:
                value = float(number)
            except ValueError:
                break
            if value <= 0:
                break
            return int(value * units[unit])
    raise UserError("Size should look like 200KB or 1.5MB.")


def parse_page_ranges(text: str, page_count: int) -> list[int]:
    """'1-3, 5, 8-' → zero-based page indexes. Raises UserError when invalid."""
    pages: list[int] = []
    for raw in text.replace(" ", "").split(","):
        if not raw:
            continue
        try:
            if "-" in raw:
                a, b = raw.split("-", 1)
                start = int(a) if a else 1
                end = int(b) if b else page_count
            else:
                start = end = int(raw)
        except ValueError:
            raise UserError("Pages should look like 1-3, 5, 8-.") from None
        if start < 1 or end > page_count or start > end:
            raise UserError(f"Pages must be between 1 and {page_count}.")
        pages.extend(range(start - 1, end))
    if not pages:
        raise UserError("No pages selected.")
    return pages


def output_folder(ctx: JobContext, source: Path, name: str) -> Path:
    """A new unique folder next to `source` for multi-file results."""
    folder = safe_io.make_unique_dir(ctx.output_dir_for(source), name, ctx.limits)
    ctx.outputs.append(folder)
    return folder


def save_into(ctx: JobContext, produced: Path, folder: Path, filename: str) -> Path:
    """Commit a temp file into a folder this job created (it is already in ctx.outputs)."""
    ctx.check_cancel()
    return safe_io.commit_file(produced, folder, filename, ctx.limits)
