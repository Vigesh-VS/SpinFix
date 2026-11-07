# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Add `--hash=sha256:` lines to a pip-compile lock file using PyPI's published digests.

pip-compile --generate-hashes downloads every wheel for every platform to hash it, which
takes very long for packages like PySide6 or lxml. PyPI already publishes the SHA-256 of
every file, so this script reads them from the PyPI JSON API instead (HTTPS, pypi.org only).
The result is the same: pip refuses to install anything whose hash doesn't match.

    pip-compile --strip-extras -o requirements.lock requirements.in
    python scripts/add_hashes.py requirements.lock
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)(\s*;[^\\]*)?\s*$")
API = "https://pypi.org/pypi/{name}/{version}/json"


def digests(name: str, version: str) -> list[str]:
    url = API.format(name=name, version=version)
    if not url.startswith("https://pypi.org/"):
        raise ValueError(url)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 — fixed https host
        data = json.load(resp)
    hashes = sorted({f["digests"]["sha256"] for f in data["urls"] if f.get("digests")})
    if not hashes:
        raise SystemExit(f"PyPI has no files for {name}=={version}")
    return hashes


def add_hashes(path: Path) -> int:
    out: list[str] = []
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PIN.match(line)
        if not match:
            out.append(line)
            continue
        name, version, marker = match.group(1), match.group(2), match.group(3) or ""
        hashes = digests(name, version)
        out.append(f"{name}=={version}{marker.rstrip()} \\")
        out.extend(
            f"    --hash=sha256:{h}" + (" \\" if i < len(hashes) - 1 else "")
            for i, h in enumerate(hashes)
        )
        count += 1
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    return count


def main(argv: list[str]) -> int:
    for arg in argv[1:]:
        print(f"{arg}: {add_hashes(Path(arg))} packages hashed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
