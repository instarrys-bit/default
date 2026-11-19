#!/usr/bin/env python3
"""Fail-closed compatibility marker for retired independent source discovery tasks."""
import json
import sys

print(json.dumps({
    "retired": True,
    "message": "Independent Source Discovery is retired; Production auto_sync owns collection and assessment."
}, ensure_ascii=False))
raise SystemExit(78)
