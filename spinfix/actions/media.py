# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Video/audio actions using an external FFmpeg (never bundled).

FFmpeg is found at an absolute, verified path: Settings → %LOCALAPPDATA%\\Spinfix\\tools →
the winget install location. Never via PATH or the current folder (DLL/binary hijacking).
All calls use an argument list, no shell, a timeout, `file:` URLs for paths (so a file
named `-rf.mp4` can't become an option) and a protocol whitelist limited to local files.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess  # nosec B404
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import ClassVar

from spinfix.actions.common import for_each
from spinfix.core import safe_io
from spinfix.core.errors import CancelledError, UserError, app_data_dir, get_logger
from spinfix.core.filetype import Category, FileInfo, Kind
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

log = get_logger("media")

MISSING = (
    "Video tools need FFmpeg. Install it with: winget install Gyan.FFmpeg "
    "(or set its path in Settings)."
)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_cache_lock = threading.Lock()
_cache: dict[str, Path | None] = {}


def _configured_path() -> str:
    from spinfix.core.settings import store  # noqa: PLC0415 — avoid import cycle at load

    return store.get().ffmpeg_path


def _candidates(configured: str) -> list[Path]:
    found: list[Path] = []
    if configured:
        p = Path(configured)
        found.append(p / "ffmpeg.exe" if p.is_dir() else p)
    tools = app_data_dir() / "tools"
    found += [tools / "ffmpeg" / "bin" / "ffmpeg.exe", tools / "ffmpeg.exe"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        with contextlib.suppress(OSError):
            for pkg in sorted(packages.glob("Gyan.FFmpeg*"), reverse=True):
                found += sorted(pkg.glob("*/bin/ffmpeg.exe"), reverse=True)
        found.append(Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
    for env in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            found.append(Path(base) / "ffmpeg" / "bin" / "ffmpeg.exe")
    return found


def _verify(exe: Path) -> Path | None:
    try:
        real = exe.resolve(strict=True)
    except OSError:
        return None
    if not real.is_absolute() or not real.is_file() or real.suffix.lower() != ".exe":
        return None
    try:
        # Absolute verified path, argument list, no shell, timeout.
        out = subprocess.run(  # noqa: S603  # nosec B603
            [str(real), "-hide_banner", "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return real if out.returncode == 0 and out.stdout.startswith("ffmpeg version") else None


def find_ffmpeg(refresh: bool = False) -> Path | None:
    configured = _configured_path()
    with _cache_lock:
        if not refresh and configured in _cache:
            return _cache[configured]
        result = next((r for c in _candidates(configured) if (r := _verify(c))), None)
        _cache[configured] = result
        if result:
            log.info("ffmpeg found")
        return result


def find_ffprobe() -> Path | None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return None
    probe = ffmpeg.with_name("ffprobe.exe")
    return probe if probe.is_file() else None


def file_url(path: Path) -> str:
    return "file:" + str(path.resolve())


def probe(path: Path) -> dict[str, object]:
    exe = find_ffprobe()
    if exe is None:
        raise UserError(MISSING)
    # Absolute verified path, argument list, no shell, timeout.
    out = subprocess.run(  # noqa: S603  # nosec B603
        [
            str(exe),
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_url(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    if out.returncode != 0:
        raise UserError(f"FFmpeg couldn't read {path.name}. It may be damaged.")
    data = json.loads(out.stdout or "{}")
    return data if isinstance(data, dict) else {}


def duration_seconds(info: dict[str, object]) -> float:
    fmt = info.get("format")
    if isinstance(fmt, dict):
        with contextlib.suppress(TypeError, ValueError):
            return float(fmt.get("duration", 0))
    return 0.0


def has_stream(info: dict[str, object], kind: str) -> bool:
    streams = info.get("streams")
    return isinstance(streams, list) and any(
        isinstance(s, dict) and s.get("codec_type") == kind for s in streams
    )


def run_ffmpeg(
    args: list[str],
    ctx: JobContext,
    duration: float,
    progress: Callable[[float], None],
    span: tuple[float, float] = (0.0, 1.0),
    cwd: Path | None = None,
) -> None:
    """Run FFmpeg with progress; kill it on cancel or timeout."""
    exe = find_ffmpeg()
    if exe is None:
        raise UserError(MISSING)
    cmd = [
        str(exe),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        *args,
    ]
    # Absolute verified path, argument list, no shell, timeout.
    proc = subprocess.Popen(  # noqa: S603  # nosec B603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or ctx.temp_dir,
        creationflags=CREATE_NO_WINDOW,
    )
    stderr_tail: list[str] = []

    def read_err() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_tail.append(line.strip())
            del stderr_tail[:-20]

    err_thread = threading.Thread(target=read_err, daemon=True)
    err_thread.start()

    def watchdog() -> None:
        ctx.cancel_event.wait(ctx.limits.external_tool_timeout_seconds)
        if proc.poll() is None:
            proc.kill()

    threading.Thread(target=watchdog, daemon=True).start()
    if proc.stdout is None:  # always set: stdout=PIPE
        raise RuntimeError("no FFmpeg output pipe")
    a, b = span
    for line in proc.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and duration > 0:
            with contextlib.suppress(ValueError):
                done = int(value) / 1_000_000 / duration
                progress(a + (b - a) * max(0.0, min(1.0, done)))
    proc.wait()
    err_thread.join(5)
    if ctx.cancel_event.is_set():
        raise CancelledError()
    if proc.returncode != 0:
        log.warning("ffmpeg failed rc=%s: %s", proc.returncode, " | ".join(stderr_tail[-3:]))
        raise UserError("FFmpeg couldn't process this file. It may be damaged or unusual.")


class MediaAction(Action):
    categories: ClassVar[frozenset[Category]] = frozenset({Category.VIDEO, Category.AUDIO})
    needs = "ffmpeg"

    def available(self) -> str | None:
        return None if find_ffmpeg() else MISSING

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        return for_each(inputs, ctx, lambda info, sub: self.one(info, options, ctx, sub))

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        raise NotImplementedError


class ExtractAudio(MediaAction):
    wheel = Wheel.CONVERT

    def __init__(self, fmt: str, order: int) -> None:
        self.fmt = fmt
        self.id = f"media.to_{fmt}"  # type: ignore[misc]
        self.title = fmt.upper()  # type: ignore[misc]
        self.icon = "audio"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        own = {"mp3": Kind.MP3, "m4a": Kind.M4A, "wav": Kind.WAV}.get(fmt)
        all_media = {
            k
            for k in Kind
            if k.value in {"mp4", "mov", "mkv", "webm", "avi", "mp3", "m4a", "wav", "flac", "ogg"}
        }
        self.kinds = frozenset(all_media - {own} if own else all_media)  # type: ignore[misc]
        self.categories = frozenset()  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        meta = probe(info.path)
        if not has_stream(meta, "audio"):
            raise UserError(f"{info.path.name} has no sound.")
        codec = {
            "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
            "m4a": ["-c:a", "aac", "-b:a", "192k"],
            "wav": ["-c:a", "pcm_s16le"],
        }[self.fmt]
        tmp = ctx.temp_file(f"audio.{self.fmt}")
        run_ffmpeg(
            [
                "-protocol_whitelist",
                "file",
                "-i",
                file_url(info.path),
                "-vn",
                "-sn",
                "-dn",
                "-map_metadata",
                "0",
                *codec,
                file_url(tmp),
            ],
            ctx,
            duration_seconds(meta),
            sub,
        )
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, f".{self.fmt}"))]


AUDIO_KBPS = 96


class CompressVideo(MediaAction):
    """Two-pass H.264 to fit a size such as 16 MB for WhatsApp."""

    wheel = Wheel.TOOLS
    categories = frozenset({Category.VIDEO})

    def __init__(self, label: str, megabytes: int, order: int) -> None:
        self.megabytes = megabytes
        self.id = f"media.fit_{megabytes}mb"  # type: ignore[misc]
        self.title = label  # type: ignore[misc]
        self.icon = "compress"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        target = self.megabytes * 1024 * 1024
        if info.size <= target:
            raise UserError(f"{info.path.name} is already under {self.megabytes} MB.")
        meta = probe(info.path)
        duration = duration_seconds(meta)
        if duration <= 0:
            raise UserError("Spinfix couldn't tell how long this video is.")
        audio = has_stream(meta, "audio")
        total_kbps = target * 8 * 0.94 / duration / 1000  # 6 % container overhead
        video_kbps = int(total_kbps - (AUDIO_KBPS if audio else 0))
        if video_kbps < 80:
            raise UserError(
                f"This video is too long to fit in {self.megabytes} MB. Try trimming it first."
            )
        height = 1080 if video_kbps > 4000 else 720 if video_kbps > 1200 else 480
        if video_kbps < 400:
            height = 360
        scale = f"scale=-2:'min({height},ih)'"
        safe_io.check_free_space(ctx.temp_dir, target * 2, ctx.limits)
        tmp = ctx.temp_file("video.mp4")
        passlog = str(ctx.temp_dir / "pass")
        common = [
            "-protocol_whitelist",
            "file",
            "-i",
            file_url(info.path),
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-b:v",
            f"{video_kbps}k",
            "-maxrate",
            f"{int(video_kbps * 1.5)}k",
            "-bufsize",
            f"{video_kbps * 2}k",
            "-vf",
            scale,
            "-pix_fmt",
            "yuv420p",
            "-passlogfile",
            passlog,
        ]
        run_ffmpeg(
            [*common, "-pass", "1", "-an", "-f", "null", "NUL"], ctx, duration, sub, (0.0, 0.45)
        )
        audio_args = ["-map", "0:a:0?", "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k"] if audio else []
        run_ffmpeg(
            [*common, "-pass", "2", *audio_args, "-movflags", "+faststart", file_url(tmp)],
            ctx,
            duration,
            sub,
            (0.45, 1.0),
        )
        label = f"{self.megabytes}MB"
        out = ctx.save(tmp, info.path, safe_io.output_name(info.path, ".mp4", label))
        if out.stat().st_size > target:
            ctx.notes.append(
                f"Came out at {safe_io.human_size(out.stat().st_size)} — a little over the target."
            )
        return [out]


def register(registry: Registry) -> None:
    registry.register(ExtractAudio("mp3", 40))
    registry.register(ExtractAudio("m4a", 41))
    registry.register(ExtractAudio("wav", 42))
    registry.register(CompressVideo("WhatsApp 16 MB", 16, 10))
    registry.register(CompressVideo("Email 25 MB", 25, 11))
    registry.register(CompressVideo("100 MB", 100, 12))
