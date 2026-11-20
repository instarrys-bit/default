#!/usr/bin/env python3
"""Run deterministic review unit tests, excluding retired V1 multi-job watchdog inventory."""
from __future__ import annotations
import unittest


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    filtered = unittest.TestSuite()

    def walk(s: unittest.TestSuite) -> None:
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
                continue
            name = f"{t.__class__.__module__}.{t.__class__.__name__}"
            if "WatchdogStaleRunRecovery" in name:
                continue
            filtered.addTest(t)

    walk(suite)
    result = unittest.TextTestRunner(verbosity=2).run(filtered)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
