#!/usr/bin/env python3
"""Run the complete repository test suite without a curated module allowlist.

The production preflight must exercise every discovered test under tests/.
Retired workflow contracts must be updated to the current four-workflow
architecture; they must not be silently excluded from CI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    print("Running the complete tests/ tree with unittest discovery; no test modules are excluded.")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
