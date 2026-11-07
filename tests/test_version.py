# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
import re
import subprocess
import sys

import pytest

from spinfix import __version__
from spinfix.cli import main


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert capsys.readouterr().out.strip() == f"Spinfix {__version__}"


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"Spinfix {__version__}"


def test_python_m_spinfix() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "spinfix"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == f"Spinfix {__version__}"


def test_core_does_not_import_qt() -> None:
    code = (
        "import sys, spinfix.core; "
        "sys.exit(any(m.startswith(('PySide6', 'PyQt')) for m in sys.modules))"
    )
    result = subprocess.run(  # noqa: S603 — fixed argument list, no shell
        [sys.executable, "-c", code], timeout=30, check=False
    )
    assert result.returncode == 0
