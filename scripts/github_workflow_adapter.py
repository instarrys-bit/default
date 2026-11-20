#!/usr/bin/env python3
"""GitHub Actions workflow dispatch and run-correlation primitives.

Production use is gated by the scheduler's reviewed adapter, caller allowlist,
allowlisted ref, persisted dispatch intent, and independent run verifier.
"""
from __future__ import annotations


import argparse
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class WorkflowAPIError(RuntimeError):
    """GitHub rejected a workflow adapter request."""


class WorkflowDispatchOutcomeUnknown(WorkflowAPIError):
    """The dispatch request may have reached GitHub, but no response was received."""


class WorkflowDispatchRejected(WorkflowAPIError):
    """GitHub explicitly rejected a dispatch request; retry may be safe."""


class WorkflowCommitMismatch(WorkflowAPIError):
    """A correlated run used a ref revision other than the one authorized by its task."""


class AmbiguousWorkflowRun(WorkflowAPIError):
    """More than one run matches a task correlation marker."""


def utc_stamp(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
