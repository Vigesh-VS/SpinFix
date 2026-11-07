# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Command-line interface.

spinfix list <files>                       which actions fit these files
spinfix run <action> <files> [-o k=v]      run an action
spinfix actions                            every action id
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from spinfix import __version__
from spinfix.core import filetype
from spinfix.core.errors import UserError, setup_logging
from spinfix.core.filetype import FileInfo
from spinfix.core.jobs import Job
from spinfix.core.limits import DEFAULT_LIMITS
from spinfix.core.registry import WHEEL_TITLES
from spinfix.core.settings import store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spinfix",
        description="Convert, compress or fix files — offline.",
    )
    parser.add_argument("--version", action="version", version=f"Spinfix {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="show which actions fit these files")
    p_list.add_argument("files", nargs="+", type=Path)

    p_run = sub.add_parser("run", help="run an action on files")
    p_run.add_argument("action")
    p_run.add_argument("files", nargs="+", type=Path)
    p_run.add_argument(
        "-o",
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="action option, e.g. -o target_size=200KB -o pages=1-3",
    )
    p_run.add_argument("-y", "--yes", action="store_true", help="don't ask for big batches")

    sub.add_parser("actions", help="list every action id")
    return parser


def _inputs(paths: Sequence[Path]) -> list[FileInfo]:
    infos: list[FileInfo] = []
    for p in paths:
        path = p.expanduser().resolve()
        if not path.exists():
            raise UserError(f"{p} doesn't exist.")
        infos.append(filetype.check(path))
    return infos


def _options(pairs: Sequence[str]) -> dict[str, object]:
    options: dict[str, object] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise UserError(f"Option {pair!r} should look like key=value.")
        options[key.strip()] = value.strip()
    return options


def _print_progress(fraction: float, message: str) -> None:
    if not sys.stderr.isatty():
        return
    line = f"\r{int(fraction * 100):3d}%  {message[:60]:<60}"
    sys.stderr.write(line)
    sys.stderr.flush()


def cmd_list(paths: Sequence[Path]) -> int:
    from spinfix.actions import build_registry  # noqa: PLC0415 — heavy imports on demand

    infos = _inputs(paths)
    for info in infos:
        print(f"{info.path.name}: {info.kind.value} ({info.category.value})")
    registry = build_registry()
    for wheel in registry.wheels_for(infos):
        print(f"\n{WHEEL_TITLES[wheel]}:")
        for action in registry.for_files(infos, wheel):
            note = action.available()
            extra = f"  [needs {action.asks}]" if action.asks else ""
            print(f"  {action.id:<24} {action.title}{extra}{'  (unavailable)' if note else ''}")
    return 0


def cmd_run(action_id: str, paths: Sequence[Path], pairs: Sequence[str], yes: bool) -> int:
    from spinfix.actions import build_registry  # noqa: PLC0415

    registry = build_registry()
    action = registry.get(action_id)
    infos = _inputs(paths)
    settings = store.get()
    if len(infos) > DEFAULT_LIMITS.batch_confirm_above and not yes:
        raise UserError(f"That's {len(infos)} files. Add --yes to go ahead.")
    if not action.accepts(infos):
        raise UserError(f"{action.title} doesn't work on these files.")
    options = _options(pairs)
    if action.id.startswith("image.to_"):
        options.setdefault("quality", settings.jpeg_quality)
    if action.id.startswith("pdf.to_") and action.id != "pdf.to_txt":
        options.setdefault("dpi", settings.pdf_dpi)
    job = Job(action, infos, options, output_subfolder=settings.output_subfolder())
    result = job.run(_print_progress)
    sys.stderr.write("\r" + " " * 70 + "\r")
    if result.clipboard_text is not None or result.clipboard_files:
        from spinfix.platform.windows import clipboard  # noqa: PLC0415

        if result.clipboard_text is not None:
            clipboard.set_text(result.clipboard_text)
            print(result.clipboard_text)
        if result.clipboard_files:
            clipboard.set_files(result.clipboard_files)
        print("(copied to the clipboard)")
    for out in result.outputs:
        print(out)
    for note in result.notes:
        print(note, file=sys.stderr)
    if not result.ok:
        print(result.message, file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.command is None:
        print(f"Spinfix {__version__}")
        return 0
    setup_logging()
    try:
        if args.command == "list":
            return cmd_list(args.files)
        if args.command == "run":
            return cmd_run(args.action, args.files, args.option, args.yes)
        if args.command == "actions":
            from spinfix.actions import build_registry  # noqa: PLC0415

            for action in build_registry().all():
                print(f"{action.id:<24} {WHEEL_TITLES[action.wheel]:<8} {action.title}")
            return 0
    except UserError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
