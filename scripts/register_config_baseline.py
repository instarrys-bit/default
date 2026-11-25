#!/usr/bin/env python3
"""Create a runner-local review proposal for uu.conf baseline changes."""
from __future__ import annotations


import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"
CONFIG = ROOT / "modules" / "uu.conf"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def build_release_pin_updates(root: Path, config_path: str, config_sha: str) -> tuple[str, str, str]:
    """Prepare consistent release, workflow-map, and write-inventory pins."""
    release_path = root / "automation" / "release_manifest.json"
    workflow_map_path = root / "automation" / "production_workflow_map.json"
    write_sets_path = root / "automation" / "resource_write_sets.json"

    release = json.loads(release_path.read_text(encoding="utf-8"))
    pins = release.get("implementation_pins")
    config_pin = pins.get("config_baseline") if isinstance(pins, dict) else None
    if (not isinstance(config_pin, dict) or config_pin.get("path") != config_path
            or config_pin.get("access") != "read_only"):
        raise ValueError("release manifest must pin the same read-only owner config path")
    config_pin["git_blob_sha"] = config_sha
    # Explicitly deny automated baseline metadata writers.
    policy = release.get("execution_policy")
    if isinstance(policy, dict):
        sync = policy.get("watchdog_baseline_metadata_sync")
        if isinstance(sync, dict):
            sync["writer"] = None
            sync["trigger"] = []
            sync["authorization"] = "No automated repository metadata synchronization is authorized."
            sync["write_allowlist"] = []
    release_text = json.dumps(release, ensure_ascii=False, indent=2) + "\n"
    release_sha = git_blob_sha(release_text.encode("utf-8"))

    workflow_map = json.loads(workflow_map_path.read_text(encoding="utf-8"))
    review_context = workflow_map.get("review_context")
    if not isinstance(review_context, dict) or not isinstance(review_context.get("release_manifest_blob_sha"), str):
        raise ValueError("production workflow map is missing its release-manifest blob pin")
    review_context["release_manifest_blob_sha"] = release_sha
    workflow_map_text = json.dumps(workflow_map, ensure_ascii=False, indent=2) + "\n"

    write_sets = json.loads(write_sets_path.read_text(encoding="utf-8"))
    protected = write_sets.get("policy", {}).get("protected_config", {})
    sync = protected.get("metadata_only_sync")
    if isinstance(sync, dict):
        sync["writer"] = None
        sync["allowed_paths"] = []
        sync["authorization"] = (
            "Baseline SHA and release metadata changes require a separately reviewed pull request. "
            "Automation may only emit a runner-local proposal."
        )
        sync["fence"] = "No automated repository writer; proposal is confined to RUNNER_TEMP."
    write_context = write_sets.get("review_context")
    if not isinstance(write_context, dict) or not isinstance(write_context.get("release_manifest_blob_sha"), str):
        raise ValueError("resource write inventory is missing its release-manifest blob pin")
    write_context["release_manifest_blob_sha"] = release_sha
    write_sets_text = json.dumps(write_sets, ensure_ascii=False, indent=2) + "\n"
    return release_text, workflow_map_text, write_sets_text


def config_change_history(guard: dict) -> list[str]:
    """Read the committed uu.conf history without author-based approval."""
    path = str(guard.get("path", "modules/uu.conf"))
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    anchor = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) == 40:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", anchor, head],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        if ancestry.returncode == 0:
            history = subprocess.run(
                ["git", "log", "--format=%H", f"{anchor}..{head}", "--", path],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            commits = [line.strip() for line in history.stdout.splitlines() if line.strip()]
            if commits:
                return commits
    latest = subprocess.run(
        ["git", "log", "-1", "--format=%H", "HEAD", "--", path],
        cwd=ROOT, check=False, capture_output=True, text=True,
    ).stdout.strip()
    return [latest] if latest else [head]


def write_baseline_proposal(proposal: dict) -> Path:
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    configured = os.environ.get("CONFIG_BASELINE_PROPOSAL_PATH")
    destination = Path(configured).resolve() if configured else temp_root / "config-baseline-proposal.json"
    if destination != temp_root and temp_root not in destination.parents:
        raise ValueError("config baseline proposal must remain under RUNNER_TEMP")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()  # Deliberately exposes no repository-write option.

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    if guard.get("path") != "modules/uu.conf" or guard.get("content_immutable_to_automation") is not True:
        raise ValueError("managed config protection invariant is invalid")

    config_bytes = CONFIG.read_bytes()
    actual = git_blob_sha(config_bytes)
    committed = subprocess.run(
        ["git", "rev-parse", f"HEAD:{guard['path']}"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual != committed:
        raise ValueError("working-tree modules/uu.conf differs from the committed Git blob; refusing proposal")

    previous = str(guard.get("approved_git_blob_sha", ""))
    if actual == previous:
        print(json.dumps({
            "status": "no_change",
            "blob_sha": actual,
            "proposal_created": False,
            "repository_files_modified": False,
            "config_file_modified": False,
        }, sort_keys=True))
        return 0

    commits = config_change_history(guard)
    actor = os.environ.get("GITHUB_ACTOR", "unknown")
    now = datetime.now(timezone.utc).isoformat()
    metadata = guard.setdefault("baseline_metadata_policy", {})
    metadata.update({
        "automation_may_read_file": True,
        "automation_may_identify_file": True,
        "automation_may_hash_file": True,
        "automation_may_diff_file": True,
        "automation_may_update_registered_blob_sha": False,
        "automation_may_update_release_baseline_sha": False,
        "automation_may_update_approved_baseline_sha": False,
        "reviewed_pr_required": True,
        "proposal_generation_mode": "runner_local_only",
        "update_authorization": (
            "Only a separately reviewed pull request may update the approved uu.conf Blob SHA "
            "or derived Release baseline pins. Automation may read, hash, diff and emit a proposal "
            "under RUNNER_TEMP, but may not write repository metadata or modules/uu.conf."
        ),
        "registration_must_not_write_config_content": True,
    })
    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "Observed config SHA change; baseline metadata requires a separately reviewed pull request.",
        "approval_mode": "reviewed_pull_request_required",
        "config_change_commits": commits,
        "actor": actor,
        "commit_sha": commits[0] if commits else "",
        "registered_at": now,
    }

    release_text, map_text, sets_text = build_release_pin_updates(ROOT, guard["path"], actual)
    proposed = {
        "sources/policy.json": policy,
        "automation/release_manifest.json": json.loads(release_text),
        "automation/production_workflow_map.json": json.loads(map_text),
        "automation/resource_write_sets.json": json.loads(sets_text),
    }
    proposal = {
        "schema_version": 1,
        "status": "requires_reviewed_pr",
        "path": guard["path"],
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "actor": actor,
        "approval_mode": "reviewed_pull_request_required",
        "config_change_commits": commits,
        "proposed_updates": proposed,
        "repository_files_modified": False,
        "config_file_modified": False,
    }
    proposal_path = write_baseline_proposal(proposal)
    print(json.dumps({
        "status": "proposal_created_requires_reviewed_pr",
        "proposal_created": True,
        "proposal_path": str(proposal_path),
        "path": guard["path"],
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "actor": actor,
        "config_change_commits": commits,
        "repository_files_modified": False,
        "config_file_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
