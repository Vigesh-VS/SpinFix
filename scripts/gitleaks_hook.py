# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""pre-commit hook: scan staged changes with gitleaks (installed via winget)."""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    exe = shutil.which("gitleaks")
    if exe is None:
        print("gitleaks not found. Install it with: winget install Gitleaks.Gitleaks")
        return 1
    exe_path = Path(exe).resolve(strict=True)
    result = subprocess.run(  # noqa: S603 — fixed arguments, absolute resolved path
        [str(exe_path), "git", "--pre-commit", "--staged", "--redact", "--no-banner"],
        timeout=120,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
