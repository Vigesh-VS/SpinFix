# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""commit-msg hook: reject AI attribution lines (CLAUDE.md §1)."""

import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"co-authored-by:|claude-session:|generated with|🤖",
    re.IGNORECASE,
)


def main(argv: list[str]) -> int:
    text = Path(argv[1]).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    bad = [ln for ln in lines if FORBIDDEN.search(ln)]
    if bad:
        print("Commit message contains forbidden attribution lines:")
        for ln in bad:
            print(f"  {ln}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
