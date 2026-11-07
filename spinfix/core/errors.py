# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Error types and logging setup.

`UserError` carries a short, friendly sentence that is shown to the user as-is.
Anything else is an internal error: it is logged and the user sees `GENERIC_MESSAGE`.
Logs never contain file contents, and paths are shortened to `…\\name.ext`.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path, PurePath

GENERIC_MESSAGE = "Something went wrong — details are in the log."
LOG_NAME = "spinfix"


class SpinfixError(Exception):
    """Base class for all Spinfix errors."""


class UserError(SpinfixError):
    """An expected problem the user can understand and act on."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CancelledError(SpinfixError):
    """The job was cancelled by the user or hit its timeout."""

    def __init__(self, message: str = "Cancelled.") -> None:
        super().__init__(message)
        self.message = message


def user_message(exc: BaseException) -> str:
    """The text to show the user for an exception."""
    if isinstance(exc, UserError | CancelledError):
        return exc.message
    return GENERIC_MESSAGE


def short_path(path: str | os.PathLike[str]) -> str:
    """Shorten a path for logs and messages: `C:\\Users\\me\\a\\photo.jpg` → `…\\photo.jpg`."""
    name = PurePath(os.fspath(path)).name
    return f"…\\{name}" if name else "…"


def app_data_dir() -> Path:
    """`%LOCALAPPDATA%\\Spinfix` (or `~/.spinfix` when LOCALAPPDATA is not set)."""
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Spinfix" if base else Path.home() / ".spinfix"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOG_NAME if name is None else f"{LOG_NAME}.{name}")


def setup_logging(level: int | str = logging.INFO, log_dir: Path | None = None) -> Path:
    """Log to a rotating file (1 MB x 3). Returns the log file path. Safe to call twice."""
    directory = log_dir if log_dir is not None else app_data_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "spinfix.log"
    logger = get_logger()
    logger.setLevel(level)
    for handler in list(logger.handlers):
        if getattr(handler, "_spinfix", False):
            logger.removeHandler(handler)
            handler.close()
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._spinfix = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.propagate = False
    return log_file
