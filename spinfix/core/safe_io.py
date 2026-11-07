# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Safe file output: clean names, unique names, atomic writes, private temp folders.

Rules (CLAUDE.md §5):
- never overwrite anything: outputs get `name (1).ext` when the name is taken;
- write to `.~name.part` in the target folder, then rename into place;
- never write outside the target folder or through a symlink/junction;
- temp work lives in `%LOCALAPPDATA%\\Spinfix\\tmp\\<random>` and is deleted after each job.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from spinfix.core.errors import UserError, app_data_dir, get_logger, short_path
from spinfix.core.limits import DEFAULT_LIMITS, Limits

log = get_logger("safe_io")

PART_PREFIX = ".~"
PART_SUFFIX = ".part"
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{i}" for i in (*range(1, 10), "¹", "²", "³")),
    *(f"LPT{i}" for i in (*range(1, 10), "¹", "²", "³")),
}
_MAX_COLLISIONS = 10_000


def sanitize_name(name: str, fallback: str = "file") -> str:
    """Make a single file name safe on Windows. Never returns an empty or reserved name."""
    name = unicodedata.normalize("NFC", name)
    name = _BAD_CHARS.sub("_", name)
    # Windows silently drops trailing dots and spaces; strip them (and leading spaces).
    name = name.strip(" ").rstrip(". ")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if stem.split(".")[0].upper().rstrip() in _RESERVED:
        stem = f"_{stem}"
    if not stem or stem in {".", ".."}:
        stem = fallback
    name = f"{stem}.{ext}" if ext else stem
    return name[:200] if len(name) > 200 else name


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def ensure_safe_dir(directory: Path) -> Path:
    """Resolve a target folder and refuse symlinks/junctions anywhere on the way."""
    if not directory.is_absolute():
        raise UserError("Spinfix needs a full folder path.")
    for part in (directory, *directory.parents):
        if part.exists() and _is_link(part) and part != part.parent:
            raise UserError(f"Spinfix won't write through a link ({short_path(part)}).")
    if not directory.is_dir():
        raise UserError(f"The folder {short_path(directory)} doesn't exist.")
    return directory.resolve(strict=True)


def _candidate(directory: Path, stem: str, suffix: str, n: int) -> Path:
    name = f"{stem}{suffix}" if n == 0 else f"{stem} ({n}){suffix}"
    return directory / name


def _fit_length(directory: Path, stem: str, suffix: str, limits: Limits) -> str:
    # Room for the folder, separator, " (9999)" and the extension.
    room = limits.max_path_length - len(str(directory)) - 1 - len(suffix) - 7
    if room < 1:
        raise UserError("The folder path is too long for a new file. Try a shorter folder.")
    return stem[:room]


def unique_path(directory: Path, filename: str, limits: Limits = DEFAULT_LIMITS) -> Path:
    """A path in `directory` that doesn't exist yet: `name.ext`, `name (1).ext`, …"""
    directory = ensure_safe_dir(directory)
    clean = Path(sanitize_name(filename))
    suffix = clean.suffix
    stem = _fit_length(directory, clean.stem, suffix, limits)
    for n in range(_MAX_COLLISIONS):
        candidate = _candidate(directory, stem, suffix, n)
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise UserError("Too many files with the same name in this folder.")


def make_unique_dir(directory: Path, name: str, limits: Limits = DEFAULT_LIMITS) -> Path:
    """Create a new empty folder `name`, `name (1)`, … inside `directory`."""
    for _ in range(_MAX_COLLISIONS):
        target = unique_path(directory, name, limits)
        try:
            target.mkdir()
        except FileExistsError:
            continue
        return target
    raise UserError("Too many folders with the same name here.")


def output_name(source: Path, new_suffix: str | None = None, label: str = "") -> str:
    """`photo.heic` + `.jpg` → `photo.jpg`; with label "small" → `photo small.jpg`."""
    stem = source.stem + (f" {label}" if label else "")
    suffix = new_suffix if new_suffix is not None else source.suffix
    return f"{stem}{suffix.lower()}"


def _within(directory: Path, path: Path) -> bool:
    try:
        return path.resolve(strict=False).parent == directory
    except OSError:
        return False


class AtomicOutput:
    """Write a file to `.~name.part` and move it to a unique final name on commit."""

    def __init__(self, directory: Path, filename: str, limits: Limits = DEFAULT_LIMITS) -> None:
        self.directory = ensure_safe_dir(directory)
        self.filename = sanitize_name(filename)
        self.limits = limits
        planned = unique_path(self.directory, self.filename, limits)
        fd, tmp = tempfile.mkstemp(
            prefix=f"{PART_PREFIX}{planned.stem[:40]}.", suffix=PART_SUFFIX, dir=self.directory
        )
        os.close(fd)
        self.temp_path = Path(tmp)
        _hide(self.temp_path)
        self.final_path: Path | None = None

    def open(self) -> BinaryIO:
        """Open the hidden temp file for writing (Windows won't truncate a hidden file
        with a plain "wb" open, so open it for update and truncate)."""
        fh = self.temp_path.open("r+b")
        fh.truncate(0)
        return fh

    def commit(self) -> Path:
        """Move the finished temp file into place without ever overwriting a file."""
        if not self.temp_path.exists():
            raise UserError("The result file went missing before it could be saved.")
        for _ in range(_MAX_COLLISIONS):
            target = unique_path(self.directory, self.filename, self.limits)
            if not _within(self.directory, target):
                raise UserError("Spinfix refused to write outside the target folder.")
            try:
                # os.link fails if the target exists, so a racing file is never replaced.
                os.link(self.temp_path, target)
            except FileExistsError:
                continue
            except OSError:
                # File systems without hard links (FAT32, some network drives).
                if target.exists():
                    continue
                self.temp_path.rename(target)  # on Windows rename refuses to overwrite
                _unhide(target)
                self.final_path = target
                return target
            self.temp_path.unlink()
            _unhide(target)
            self.final_path = target
            return target
        raise UserError("Too many files with the same name in this folder.")

    def discard(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.temp_path.unlink()


@contextlib.contextmanager
def atomic_output(
    directory: Path, filename: str, limits: Limits = DEFAULT_LIMITS
) -> Iterator[AtomicOutput]:
    """`with atomic_output(dir, "x.png") as out, out.open() as fh: fh.write(...)`.

    The file is committed when the block ends without an error.
    """
    out = AtomicOutput(directory, filename, limits)
    try:
        yield out
        if out.final_path is None:
            out.commit()
    except BaseException:
        out.discard()
        raise


def commit_file(src: Path, directory: Path, filename: str, limits: Limits = DEFAULT_LIMITS) -> Path:
    """Copy a finished file from the temp folder into `directory` atomically."""
    with (
        atomic_output(directory, filename, limits) as out,
        src.open("rb") as fin,
        out.open() as fout,
    ):
        shutil.copyfileobj(fin, fout, 1024 * 1024)
    if out.final_path is None:  # set by commit()
        raise RuntimeError("commit did not run")
    return out.final_path


def _set_hidden(path: Path, hidden: bool) -> None:
    if os.name != "nt":
        return
    import ctypes  # noqa: PLC0415 — Windows only

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        return
    new = (attrs | 0x2) if hidden else (attrs & ~0x2)
    ctypes.windll.kernel32.SetFileAttributesW(str(path), new)


def _hide(path: Path) -> None:
    _set_hidden(path, True)


def _unhide(path: Path) -> None:
    _set_hidden(path, False)


def remove_stale_parts(directory: Path) -> int:
    """Delete leftover `.~*.part` files Spinfix created in a folder. Returns the count."""
    count = 0
    with contextlib.suppress(OSError):
        for entry in directory.iterdir():
            if (
                entry.name.startswith(PART_PREFIX)
                and entry.name.endswith(PART_SUFFIX)
                and entry.is_file()
                and not entry.is_symlink()
            ):
                with contextlib.suppress(OSError):
                    entry.unlink()
                    count += 1
    return count


def temp_root() -> Path:
    root = app_data_dir() / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextlib.contextmanager
def job_temp_dir() -> Iterator[Path]:
    """A private temp folder for one job, deleted afterwards."""
    path = Path(tempfile.mkdtemp(prefix="job-", dir=temp_root()))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def clean_temp_root() -> None:
    """Called on startup: remove temp folders left by a crash."""
    root = temp_root()
    for entry in root.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                entry.unlink()


def check_free_space(directory: Path, needed: int, limits: Limits = DEFAULT_LIMITS) -> None:
    free = shutil.disk_usage(directory).free
    if free < needed + limits.free_space_margin_bytes:
        raise UserError(
            f"Not enough free space: needs about {human_size(needed)}, "
            f"only {human_size(free)} free."
        )


def human_size(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "bytes":
                return f"{int(n)} bytes"
            return f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1024
    return f"{n:.1f} TB"  # pragma: no cover
