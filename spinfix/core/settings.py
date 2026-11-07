# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""User settings, stored as JSON in `%APPDATA%\\Spinfix\\settings.json`.

Values are validated on load; anything unknown or invalid falls back to the default.
No secrets are ever stored here (those go to Windows Credential Manager via keyring).
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from spinfix.core.errors import get_logger

log = get_logger("settings")

TRIGGER_KEYS = ("shift", "ctrl", "alt")
OUTPUT_MODES = ("next_to", "subfolder")
MAX_SETTINGS_BYTES = 256 * 1024


@dataclass
class Settings:
    trigger_key: str = "shift"
    hotkey: str = "ctrl+alt+space"
    output_mode: str = "next_to"
    subfolder_name: str = "Spinfix"
    jpeg_quality: int = 85
    pdf_dpi: int = 150
    keep_metadata_on_convert: bool = True
    keep_metadata_on_compress: bool = False
    start_with_windows: bool = False
    first_run_done: bool = False
    show_toasts: bool = True
    paused: bool = False
    ffmpeg_path: str = ""

    def output_subfolder(self) -> str | None:
        return self.subfolder_name if self.output_mode == "subfolder" else None


_VALIDATORS: dict[str, Any] = {
    "trigger_key": lambda v: v in TRIGGER_KEYS,
    "hotkey": lambda v: isinstance(v, str) and 0 < len(v) < 40,
    "output_mode": lambda v: v in OUTPUT_MODES,
    "subfolder_name": lambda v: isinstance(v, str) and 0 < len(v.strip()) < 60,
    "jpeg_quality": lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 100,
    "pdf_dpi": lambda v: isinstance(v, int) and not isinstance(v, bool) and 36 <= v <= 600,
    "ffmpeg_path": lambda v: isinstance(v, str) and len(v) < 1000,
}


def _valid(name: str, value: Any, default: Any) -> bool:
    check = _VALIDATORS.get(name)
    if check is not None:
        return bool(check(value))
    return type(value) is type(default)


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) / "Spinfix" if base else Path.home() / ".spinfix"
    return root / "settings.json"


def from_dict(data: Any) -> Settings:
    settings = Settings()
    if not isinstance(data, dict):
        return settings
    for f in fields(Settings):
        if f.name in data:
            value = data[f.name]
            if _valid(f.name, value, getattr(settings, f.name)):
                setattr(settings, f.name, value)
            else:
                log.warning("ignored invalid setting %s", f.name)
    return settings


def load(path: Path | None = None) -> Settings:
    p = path or settings_path()
    try:
        if p.stat().st_size > MAX_SETTINGS_BYTES:
            log.warning("settings file too large; using defaults")
            return Settings()
        return from_dict(json.loads(p.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError):
        log.warning("settings file unreadable; using defaults")
        return Settings()


def save(settings: Settings, path: Path | None = None) -> None:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    tmp.replace(p)  # our own file: replacing it is intended


class _Store:
    """The one place with mutable global state (CLAUDE.md §9)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._settings: Settings | None = None

    def get(self) -> Settings:
        with self._lock:
            if self._settings is None:
                self._settings = load()
            return self._settings

    def update(self, **changes: Any) -> Settings:
        with self._lock:
            current = self._settings or load()
            merged = from_dict({**asdict(current), **changes})
            self._settings = merged
            with contextlib.suppress(OSError):
                save(merged)
            return merged

    def reset_cache(self) -> None:
        with self._lock:
            self._settings = None


store = _Store()
