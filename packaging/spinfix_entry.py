# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""PyInstaller entry point for Spinfix.exe."""

import sys

from spinfix.app.main import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
