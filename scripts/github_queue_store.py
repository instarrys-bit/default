#!/usr/bin/env python3
"""Append-only GitHub Issue comment snapshots for durable automation queue state.

The repository bootstrap JSON is read-only. All queue mutations are appended as
compressed, integrity-checked Issue comments; no repository contents are written.
"""
from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MARKER = "<!-- shadowrocket-automation-queue:v1 -->"
MARKER_V2 = "<!-- shadowrocket-automation-queue:v2 -->"
DEFAULT_ISSUE_NUMBER = 423
# When Issue comments hit GitHub's 2500 ceiling, point here instead of editing code.
QUEUE_STORE_POINTER_PATH = Path(__file__).resolve().parents[1] / "automation" / "queue_store_pointer.json"
MAX_COMMENT_BYTES = 60_000
CHUNK_DATA_CHARS = 40_000
COMMENT_PAGE_BATCH_SIZE = 4


def resolve_queue_issue_number(explicit: int | None = None) -> int:
    """Resolve the active durable-queue Issue number.

    Precedence:
    1. explicit constructor argument
    2. AUTOMATION_QUEUE_ISSUE_NUMBER environment variable
    3. automation/queue_store_pointer.json active_issue_number
    4. DEFAULT_ISSUE_NUMBER (423)
    """
    if explicit is not None:
        if explicit < 1:
            raise ValueError("issue_number must be a positive integer")
        return explicit
    env_raw = os.environ.get("AUTOMATION_QUEUE_ISSUE_NUMBER")
    if env_raw is not None and str(env_raw).strip() != "":
        try:
            value = int(env_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("AUTOMATION_QUEUE_ISSUE_NUMBER must be a positive integer") from None
        if value < 1:
            raise ValueError("AUTOMATION_QUEUE_ISSUE_NUMBER must be a positive integer")
        return value
    if QUEUE_STORE_POINTER_PATH.is_file():
        try:
            pointer = json.loads(QUEUE_STORE_POINTER_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid queue store pointer at {QUEUE_STORE_POINTER_PATH}: {exc}") from exc
        if not isinstance(pointer, dict):
            raise ValueError("queue store pointer must be a JSON object")
        raw = pointer.get("active_issue_number")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("queue store pointer active_issue_number must be a positive integer") from None
        if value < 1:
            raise ValueError("queue store pointer active_issue_number must be a positive integer")
        return value
    return DEFAULT_ISSUE_NUMBER
