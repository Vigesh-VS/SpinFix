# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Zip and unzip with Spinfix's safety layer.

Unzip blocks zip-slip (`..`, absolute paths, drive letters, symlinks, reserved names),
caps total size / entry count / per-entry ratio, checks free space first and counts the
real bytes written (headers can lie). Zip never follows symlinks or junctions.
"""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from spinfix.actions.common import output_folder
from spinfix.core import safe_io
from spinfix.core.errors import UserError
from spinfix.core.filetype import Category, FileInfo, Kind
from spinfix.core.limits import Limits
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

CHUNK = 1024 * 1024


class UnsafeArchiveError(UserError):
    pass


def safe_member_path(name: str) -> PurePosixPath | None:
    """Turn an archive entry name into a safe relative path, or None to skip it."""
    cleaned = name.replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or "\x00" in cleaned:
        return None
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    if ":" in parts[0] or any(":" in p for p in parts):  # drive letters, ADS streams
        return None
    safe_parts = [safe_io.sanitize_name(p) for p in parts]
    if safe_parts != parts:
        return None  # reserved names (CON, NUL…), control chars, trailing dots
    return PurePosixPath(*safe_parts)


def _is_symlink_entry(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def check_zip(zf: zipfile.ZipFile, archive_size: int, limits: Limits) -> list[zipfile.ZipInfo]:
    """Validate the whole archive before extracting anything."""
    infos = zf.infolist()
    if len(infos) > limits.max_archive_entries:
        raise UnsafeArchiveError(
            f"This archive has too many files (over {limits.max_archive_entries})."
        )
    cap = limits.archive_size_cap(archive_size)
    total = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise UserError("This archive is password-protected. Spinfix can't open it yet.")
        total += info.file_size
        if total > cap:
            raise UnsafeArchiveError(
                f"This archive would unpack to over {safe_io.human_size(cap)}, "
                "so Spinfix stopped (it may be a zip bomb)."
            )
        if (
            info.compress_size
            and info.file_size / info.compress_size > limits.max_archive_entry_ratio
            and info.file_size > 10 * CHUNK
        ):
            raise UnsafeArchiveError("This archive looks like a zip bomb, so Spinfix stopped.")
    return infos


def extract_zip(path: Path, dest: Path, ctx: JobContext) -> tuple[int, int]:
    """Extract into `dest` (an empty folder Spinfix created). Returns (files, skipped)."""
    limits = ctx.limits
    archive_size = path.stat().st_size
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UserError(f"{path.name} looks damaged and couldn't be opened.") from exc
    with zf:
        infos = check_zip(zf, archive_size, limits)
        declared = sum(i.file_size for i in infos)
        safe_io.check_free_space(dest, declared, limits)
        cap = limits.archive_size_cap(archive_size)
        dest_root = dest.resolve()
        written_total = 0
        files = skipped = 0
        for n, info in enumerate(infos):
            ctx.progress(n / max(len(infos), 1), f"Unpacking {n + 1}/{len(infos)}")
            rel = safe_member_path(info.filename)
            if rel is None or _is_symlink_entry(info):
                skipped += 1
                continue
            target = dest_root.joinpath(*rel.parts)
            # Final guard: the resolved target must stay inside the destination.
            if not target.resolve().is_relative_to(dest_root):
                skipped += 1
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                skipped += 1  # duplicate entry name; never overwrite
                continue
            if len(str(target)) > limits.max_path_length:
                skipped += 1
                continue
            entry_written = 0
            try:
                with zf.open(info) as src, target.open("xb") as out:
                    while chunk := src.read(CHUNK):
                        entry_written += len(chunk)
                        written_total += len(chunk)
                        if written_total > cap or entry_written > info.file_size + CHUNK:
                            raise UnsafeArchiveError(
                                "This archive unpacks to more than it claims, so Spinfix "
                                "stopped (it may be a zip bomb)."
                            )
                        out.write(chunk)
                        ctx.check_cancel()
            except (zipfile.BadZipFile, EOFError, ValueError, NotImplementedError) as exc:
                target.unlink(missing_ok=True)
                raise UserError(f"{path.name} is damaged ({info.filename!r}).") from exc
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            files += 1
    return files, skipped


class Unzip(Action):
    id = "archive.unzip"
    title = "Unzip"
    icon = "unzip"
    wheel = Wheel.TOOLS
    order = 50
    kinds = frozenset({Kind.ZIP})

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        outputs: list[Path] = []
        for info in inputs:
            folder = output_folder(ctx, info.path, info.path.stem)
            files, skipped = extract_zip(info.path, folder, ctx)
            if skipped:
                ctx.notes.append(f"Skipped {skipped} unsafe or duplicate entries.")
            outputs.append(folder)
            if files == 0 and not skipped:
                ctx.notes.append(f"{info.path.name} was empty.")
        return outputs


def _walk(root: Path) -> list[Path]:
    """All files under a folder, never following links or junctions."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames if not (here / d).is_symlink() and not (here / d).is_junction()
        ]
        found.extend(here / f for f in filenames if not (here / f).is_symlink())
    return found


class Zip(Action):
    id = "archive.zip"
    title = "Zip"
    icon = "zip"
    wheel = Wheel.SHARE
    order = 30
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        first = inputs[0].path
        name = f"{first.stem if first.is_file() else first.name}.zip"
        if len(inputs) > 1:
            name = f"{first.parent.name or 'Archive'}.zip"
        entries: list[tuple[Path, str]] = []
        for info in inputs:
            if info.path.is_dir():
                if info.path.is_symlink() or info.path.is_junction():
                    continue
                base = info.path.parent
                entries += [(f, f.relative_to(base).as_posix()) for f in _walk(info.path)]
            else:
                entries.append((info.path, info.path.name))
        if len(entries) > ctx.limits.max_archive_entries:
            raise UserError("Too many files to zip at once.")
        total = sum(f.stat().st_size for f, _ in entries)
        safe_io.check_free_space(ctx.temp_dir, total, ctx.limits)
        tmp = ctx.temp_file("archive.zip")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            done = 0
            seen: set[str] = set()
            for f, arc in entries:
                if arc.lower() in seen:
                    continue
                seen.add(arc.lower())
                ctx.progress(done / max(total, 1), f"Adding {f.name}")
                zinfo = zipfile.ZipInfo.from_file(f, arc)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                with f.open("rb") as src, zf.open(zinfo, "w", force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst, CHUNK)
                done += f.stat().st_size
        return [ctx.save(tmp, first, name)]


def register(registry: Registry) -> None:
    registry.register(Unzip())
    registry.register(Zip())
