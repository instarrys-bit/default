#!/usr/bin/env python3
"""Deterministically verify remote task results against reviewed adapter contracts."""
from __future__ import annotations


import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

from remote_task_queue_runtime import (
    make_store, validate_candidate, validate_envelope,
)
from task_queue_runtime import now_utc, stamp
from github_queue_store import QueueStoreError
from github_workflow_adapter import GitHubWorkflowClient, WorkflowAPIError, inspect_correlated_run
from resource_lease_runtime import release_resource_leases_in_queue

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_ID = "script_task_result_verifier"

# NOTE: Full file content continues - this is a critical restore
