#!/usr/bin/env python3
"""Capture and verify the exact production input fingerprint."""
import os
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from production_intent import load_manifest, compute_fingerprint
manifest = load_manifest(Path("automation/production_inputs.json"))
actual = compute_fingerprint(Path("."), manifest)
expected = os.environ.get("PRODUCTION_FINGERPRINT", "")
if expected and expected != actual:
    raise SystemExit("The dispatched production fingerprint does not match the checked-out input snapshot.")
with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
    stream.write(f"PRODUCTION_INPUT_FINGERPRINT={actual}\n")
print(f"Captured production input fingerprint {actual}.")
