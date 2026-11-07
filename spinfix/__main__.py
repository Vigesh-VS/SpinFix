# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Entry point: `python -m spinfix` starts the app (`python -m spinfix.cli` for the CLI)."""

import sys

from spinfix.app.main import run

sys.exit(run(sys.argv[1:]))
