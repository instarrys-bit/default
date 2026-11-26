#!/usr/bin/env python3
"""Observe uu.conf changes and, when authorized, register SHA metadata only."""
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
CONFIG_PATH = "modules/uu.conf"
WRITER = "Storage Management / File Management"
ALLOWLIST = (
    "sources/policy.json",
    "automation/release_manifest.json",
    "automation/production_workflow_map.json",
    "automation/resource_write_sets.json",
)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def run(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, check=check, capture_output=True, text=True)
    return result.stdout.strip()


def owner_approved_config_history(guard: dict) -> list[str]:
    """Return every intervening config commit only when GitHub attributes all of them to the repo owner."""
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not owner or not repository or "/" not in repository or os.environ.get("GITHUB_REF") != "refs/heads/main":
        return []
    anchor = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) != 40:
        return []
    head = run(["git", "rev-parse", "HEAD"])
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", anchor, head],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if ancestry.returncode != 0:
        return []
    commits = [item for item in run(["git", "rev-list", f"{anchor}..{head}", "--", CONFIG_PATH]).splitlines() if item]
    if not commits:
        return []
    for commit in commits:
        login = run(["gh", "api", f"repos/{repository}/commits/{commit}", "--jq", ".author.login // empty"])
        if login != owner:
            print(f"Pending baseline registration: commit {commit} is attributed to {login or '<unassociated>'}, not repository owner {owner}.", file=sys.stderr)
            return []
    return commits


def json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def build_release_pin_updates(root: Path, config_path: str, config_sha: str) -> tuple[str, str, str]:
    """Prepare the config pin and all dependent release-manifest references."""
    release_path = root / "automation" / "release_manifest.json"
    workflow_map_path = root / "automation" / "production_workflow_map.json"
    write_sets_path = root / "automation" / "resource_write_sets.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    pins = release.get("implementation_pins")
    config_pin = pins.get("config_baseline") if isinstance(pins, dict) else None
    if (not isinstance(config_pin, dict) or config_pin.get("path") != config_path
            or config_pin.get("access") != "read_only"):
        raise ValueError("release manifest must retain the read-only modules/uu.conf config pin")
    config_pin["git_blob_sha"] = config_sha

    pin_paths = {
        "baseline_registration_runtime": "scripts/register_config_baseline.py",
        "automation_write_boundary_validator": "scripts/validate_automation_write_boundary.py",
        "storage_management_workflow": ".github/workflows/storage-management.yml",
        "baseline_metadata_publisher": "scripts/publish_config_baseline_metadata.sh",
        "baseline_verifier": "scripts/verify_baseline.py",
        "storage_runtime": "storage/v2/runtime.py",
    }
    for key, path in pin_paths.items():
        pin = pins.get(key) if isinstance(pins, dict) else None
        if isinstance(pin, dict):
            pin["git_blob_sha"] = run(["git", "rev-parse", f"HEAD:{path}"])
            if key == "baseline_metadata_publisher":
                pin["status"] = "active_metadata_only_allowlist"

    execution_policy = release.setdefault("execution_policy", {})
    sync = execution_policy.setdefault("watchdog_baseline_metadata_sync", {})
    sync.update({
        "writer": WRITER,
        "trigger": ["push", "schedule"],
        "authorization": (
            "The user explicitly authorizes automatic updates to the approved modules/uu.conf Blob SHA, "
            "formal baseline SHA and derived Release SHA metadata. File Management may do so only after "
            "GitHub verifies every intervening uu.conf-changing commit since the prior approved anchor "
            "is authored by the repository owner. Only the four metadata paths in write_allowlist may be "
            "written. modules/uu.conf bytes are never writable."
        ),
        "write_allowlist": list(ALLOWLIST),
        "protected_config": "modules/uu.conf is byte-for-byte read-only to automation.",
        "stale_main_guard": (
            "Require a clean checkout at current origin/main; verify the config blob before and after; "
            "stage only the exact metadata allowlist; publish with a non-force fast-forward push."
        ),
    })
    release_text = json_text(release)
    release_sha = git_blob_sha(release_text.encode("utf-8"))

    workflow_map = json.loads(workflow_map_path.read_text(encoding="utf-8"))
    review_context = workflow_map.get("review_context")
    if not isinstance(review_context, dict) or not isinstance(review_context.get("release_manifest_blob_sha"), str):
        raise ValueError("production workflow map is missing its release-manifest blob pin")
    review_context["release_manifest_blob_sha"] = release_sha

    write_sets = json.loads(write_sets_path.read_text(encoding="utf-8"))
    protected = write_sets.get("policy", {}).get("protected_config", {})
    metadata_sync = protected.get("metadata_only_sync")
    if not isinstance(metadata_sync, dict):
        raise ValueError("resource write inventory is missing protected-config metadata_only_sync")
    metadata_sync.update({
        "writer": WRITER,
        "allowed_paths": list(ALLOWLIST),
        "authorization": (
            "User-authorized metadata-only registration by Storage Management after verifying all intervening "
            "modules/uu.conf commits are repository-owner-authored. This permission does not authorize config "
            "content changes or any production/ruleset writer."
        ),
        "fence": (
            "Dedicated main push/schedule job; full-history owner-attribution check; clean-main compare; "
            "exact four-path staging allowlist; config Blob SHA checked before/after; non-force push."
        ),
        "never_write": [CONFIG_PATH],
    })
    write_context = write_sets.get("review_context")
    if not isinstance(write_context, dict) or not isinstance(write_context.get("release_manifest_blob_sha"), str):
        raise ValueError("resource write inventory is missing its release-manifest blob pin")
    write_context["release_manifest_blob_sha"] = release_sha
    return release_text, json_text(workflow_map), json_text(write_sets)


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
    parser.add_argument("--apply", action="store_true", help="apply the exact metadata-only allowlist; Storage Management only")
    args = parser.parse_args()

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    if guard.get("path") != CONFIG_PATH or guard.get("content_immutable_to_automation") is not True:
        raise ValueError("managed config protection invariant is invalid")
    config_bytes = CONFIG.read_bytes()
    actual = git_blob_sha(config_bytes)
    committed = run(["git", "rev-parse", f"HEAD:{CONFIG_PATH}"])
    if actual != committed:
        raise ValueError("working-tree modules/uu.conf differs from the committed Git blob; refusing metadata update")
    previous = str(guard.get("approved_git_blob_sha", ""))
    if actual == previous:
        print(json.dumps({
            "status": "no_change", "blob_sha": actual,
            "repository_files_modified": False, "config_file_modified": False,
        }, sort_keys=True))
        return 0

    commits = owner_approved_config_history(guard)
    if not commits:
        proposal = {
            "schema_version": 1,
            "status": "observed_pending_owner_attribution",
            "path": CONFIG_PATH,
            "previous_blob_sha": previous,
            "observed_blob_sha": actual,
            "repository_owner": os.environ.get("GITHUB_REPOSITORY_OWNER", ""),
            "config_change_commits": [],
            "repository_files_modified": False,
            "config_file_modified": False,
            "next_action": "Keep the registered baseline unchanged; preserve this observation and continue read-only audit until the complete owner-authored commit chain can be verified.",
        }
        proposal_path = write_baseline_proposal(proposal)
        print(json.dumps({
            "status": "observed_pending_owner_attribution",
            "proposal_path": str(proposal_path),
            "previous_blob_sha": previous,
            "observed_blob_sha": actual,
            "repository_files_modified": False,
            "config_file_modified": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0

    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    actor = os.environ.get("GITHUB_ACTOR", owner)
    now = datetime.now(timezone.utc).isoformat()
    metadata = guard.setdefault("baseline_metadata_policy", {})
    metadata.update({
        "automation_may_read_file": True,
        "automation_may_identify_file": True,
        "automation_may_hash_file": True,
        "automation_may_diff_file": True,
        "automation_may_update_registered_blob_sha": True,
        "automation_may_update_release_baseline_sha": True,
        "automation_may_update_approved_baseline_sha": True,
        "reviewed_pr_required": True,
        "owner_authored_config_history_required": True,
        "metadata_writer": WRITER,
        "metadata_write_allowlist": list(ALLOWLIST),
        "proposal_generation_mode": "runner_local_only",
        "update_authorization": (
            "The user explicitly authorizes Storage Management / File Management to update the observed "
            "Blob SHA, approved baseline SHA and derived Release SHA metadata after verifying every "
            "intervening uu.conf-changing commit is authored by the repository owner. Manual metadata PRs "
            "still require human review. No automation may write modules/uu.conf content."
        ),
        "registration_must_not_write_config_content": True,
    })
    guard["description"] = (
        "Authoritative owner-managed Shadowrocket config. Storage Management may automatically register "
        "baseline SHA metadata only after verifying the complete owner-authored uu.conf commit history. "
        "Automation must never rewrite modules/uu.conf bytes."
    )
    content_protection = guard.setdefault("content_protection", {})
    content_protection["reaction_model"] = (
        "When the owner manually edits modules/uu.conf or explicitly authorizes a specific AI edit, observe "
        "the resulting Git blob SHA and commit context. Storage Management may update only the approved "
        "baseline metadata after verifying every intervening config-changing commit is repository-owner-authored. "
        "If attribution is missing or any commit is not owner-authored, keep the approved baseline unchanged, "
        "preserve the observation in a RUNNER_TEMP proposal, and continue read-only audit. Never write config bytes."
    )
    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "User-authorized automatic metadata registration after GitHub verified every intervening uu.conf-changing commit is repository-owner-authored. Config bytes remain immutable to automation.",
        "approval_mode": "owner_authored_config_history_with_user_authorization",
        "config_change_commits": commits,
        "actor": owner,
        "commit_sha": commits[0],
        "registered_at": now,
    }

    release_text, map_text, sets_text = build_release_pin_updates(ROOT, CONFIG_PATH, actual)
    updates = {
        "sources/policy.json": json_text(policy),
        "automation/release_manifest.json": release_text,
        "automation/production_workflow_map.json": map_text,
        "automation/resource_write_sets.json": sets_text,
    }
    proposal = {
        "schema_version": 1,
        "status": "owner_history_verified_metadata_update_ready",
        "path": CONFIG_PATH,
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "actor": actor,
        "approval_mode": "owner_authored_config_history_with_user_authorization",
        "config_change_commits": commits,
        "proposed_updates": {path: json.loads(content) for path, content in updates.items()},
        "repository_files_modified": False,
        "config_file_modified": False,
    }
    if not args.apply:
        proposal_path = write_baseline_proposal(proposal)
        print(json.dumps({
            "status": "proposal_created_owner_history_verified",
            "proposal_path": str(proposal_path),
            "previous_blob_sha": previous,
            "new_blob_sha": actual,
            "verified_owner_commits": commits,
            "repository_files_modified": False,
            "config_file_modified": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0

    if os.environ.get("GITHUB_EVENT_NAME") not in {"push", "schedule"} or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("--apply is restricted to the Storage Management main push/schedule job")
    if not owner or not os.environ.get("GITHUB_REPOSITORY"):
        raise ValueError("repository owner context is required for metadata registration")
    if run(["git", "status", "--porcelain"]):
        raise ValueError("metadata registration requires a clean checkout")
    for relative, content in updates.items():
        if relative not in ALLOWLIST:
            raise ValueError(f"refusing non-allowlisted metadata path: {relative}")
        (ROOT / relative).write_text(content, encoding="utf-8")
    if CONFIG.read_bytes() != config_bytes:
        raise RuntimeError("protected modules/uu.conf bytes changed during metadata registration")
    changed = [item for item in run(["git", "diff", "--name-only"]).splitlines() if item]
    unexpected = sorted(set(changed) - set(ALLOWLIST))
    if unexpected or CONFIG_PATH in changed:
        raise RuntimeError(f"metadata registration changed paths outside the exact allowlist: {unexpected or changed}")
    print(json.dumps({
        "status": "metadata_registered_pending_guarded_commit",
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "verified_owner_commits": commits,
        "modified_paths": changed,
        "repository_files_modified": True,
        "config_file_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError, RuntimeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
