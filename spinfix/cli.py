# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Command-line interface. M0: prints the version. `list` and `run` arrive in M1."""

import argparse
from collections.abc import Sequence

from spinfix import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spinfix",
        description="Convert, compress or fix files — offline.",
    )
    parser.add_argument("--version", action="version", version=f"Spinfix {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(f"Spinfix {__version__}")
    return 0
