#!/usr/bin/env python3
"""Create a runner-local review proposal for owner-approved uu.conf baseline changes."""
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
    release_text = json.dumps(release, ensure_ascii=False, indent=2) + "\n"
    release_sha = git_blob_sha(release_text.encode("utf-8"))

    workflow_map = json.loads(workflow_map_path.read_text(encoding="utf-8"))
    review_context = workflow_map.get("review_context")
    if not isinstance(review_context, dict) or not isinstance(review_context.get("release_manifest_blob_sha"), str):
        raise ValueError("production workflow map is missing its release-manifest blob pin")
    review_context["release_manifest_blob_sha"] = release_sha
    workflow_map_text = json.dumps(workflow_map, ensure_ascii=False, indent=2) + "\n"

    write_sets = json.loads(write_sets_path.read_text(encoding="utf-8"))
    write_context = write_sets.get("review_context")
    if not isinstance(write_context, dict) or not isinstance(write_context.get("release_manifest_blob_sha"), str):
        raise ValueError("resource write inventory is missing its release-manifest blob pin")
    write_context["release_manifest_blob_sha"] = release_sha
    write_sets_text = json.dumps(write_sets, ensure_ascii=False, indent=2) + "\n"
    return release_text, workflow_map_text, write_sets_text


def owner_approved_push_changed_config() -> bool:
    if os.environ.get("GITHUB_EVENT_NAME") != "push":
        return False
    actor = os.environ.get("GITHUB_ACTOR", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    before = os.environ.get("GITHUB_BEFORE", "")
    after = os.environ.get("GITHUB_SHA", "")
    if not actor or actor != owner or not before or not after or set(before) == {"0"}:
        return False
    result = subprocess.run(
        ["git", "diff", "--name-only", before, after],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return "modules/uu.conf" in result.stdout.splitlines()


def owner_approved_config_history(guard: dict) -> list[str]:
    """Recover interrupted registration only from owner-authored config commits."""
    event = os.environ.get("BASELINE_SOURCE_EVENT", os.environ.get("GITHUB_EVENT_NAME", ""))
    if event not in {"push", "workflow_dispatch", "schedule"}:
        return []
    actor = os.environ.get("GITHUB_ACTOR", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    ref = os.environ.get("BASELINE_SOURCE_REF", os.environ.get("GITHUB_REF", ""))
    if event == "push" and (not actor or actor != owner):
        return []
    if event in {"workflow_dispatch", "schedule"} and ref != "refs/heads/main":
        return []
    after = os.environ.get("BASELINE_SOURCE_SHA", os.environ.get("GITHUB_SHA", ""))
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    baseline_commit = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if (
        not owner or ref != "refs/heads/main"
        or not after or not repo or not baseline_commit
        or set(after) == {"0"} or set(baseline_commit) == {"0"}
    ):
        return []
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, after],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if ancestry.returncode != 0:
        print(f"Baseline history recovery blocked: baseline commit {baseline_commit} is not an ancestor of target {after}.", file=sys.stderr)
        return []
    history = subprocess.run(
        ["git", "log", "--format=%H", f"{baseline_commit}..{after}", "--", str(guard["path"])],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    commits = [line.strip() for line in history.stdout.splitlines() if line.strip()]
    if not commits:
        print(f"Baseline history recovery blocked: no {guard['path']} commits were found between {baseline_commit} and {after}.", file=sys.stderr)
        return []
    for commit_sha in commits:
        author = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{commit_sha}", "--jq", ".author.login // empty"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        if author != owner:
            print(f"Baseline history recovery blocked: GitHub author for config commit {commit_sha} is {author or '<unassociated>'}, expected repository owner {owner}.", file=sys.stderr)
            return []
    return commits


def write_baseline_proposal(proposal: dict) -> Path:
    temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    configured = os.environ.get("CONFIG_BASELINE_PROPOSAL_PATH")
    destination = Path(configured).resolve() if configured else temp_root / "config-baseline-proposal.json"
    if destination != temp_root and temp_root not in destination.parents:
        raise ValueError("config baseline proposal must remain under RUNNER_TEMP")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination



def apply_baseline_updates(root: Path, config_path: str, config_sha: str, policy: dict,
                           release_text: str, workflow_map_text: str, write_sets_text: str) -> list[str]:
    """Apply only owner-verified baseline metadata and prove config bytes remain unchanged."""
    config = root / config_path
    before = config.read_bytes()
    if git_blob_sha(before) != config_sha:
        raise ValueError("uu.conf changed after owner-history verification; refusing metadata sync")
    updates = {
        "sources/policy.json": json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        "automation/release_manifest.json": release_text,
        "automation/production_workflow_map.json": workflow_map_text,
        "automation/resource_write_sets.json": write_sets_text,
    }
    for relative, content in updates.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".baseline-sync-{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, destination)
    after = config.read_bytes()
    if after != before or git_blob_sha(after) != config_sha:
        raise ValueError("protected modules/uu.conf bytes changed during metadata sync")
    return sorted(updates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply owner-verified metadata-only sync; reserved for Watchdog baseline-sync.")
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    actual = git_blob_sha((ROOT / guard["path"]).read_bytes())
    previous = str(guard["approved_git_blob_sha"])
    changed = actual != previous

    # Require GitHub owner attribution for every intervening config-changing commit.
    commits = owner_approved_config_history(guard)
    if not commits:
        if changed:
            raise ValueError("uu.conf differs from the approved baseline, but every intervening owner-authored config commit could not be verified; refusing automatic approval.")
        print(json.dumps({"registered": False, "reason": "no owner-verified uu.conf baseline drift",
                          "blob_sha": actual, "config_file_modified": False}, sort_keys=True))
        return 0
    if not changed:
        print(json.dumps({"registered": False, "reason": "registered baseline already matches main",
                          "blob_sha": actual, "config_file_modified": False}, sort_keys=True))
        return 0

    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    approval_mode = "recovered_owner_authored_config_history"
    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "Watchdog synchronized the exact main-branch uu.conf Git blob after verifying every intervening config-changing commit is associated with the repository owner. Only baseline metadata and derived release pins are updated; uu.conf bytes are immutable to automation.",
        "approval_mode": approval_mode,
        "config_change_commits": commits,
        "actor": owner,
        "commit_sha": commits[0],
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    release_text, map_text, sets_text = build_release_pin_updates(ROOT, guard["path"], actual)
    proposed = {
        "sources/policy.json": policy,
        "automation/release_manifest.json": json.loads(release_text),
        "automation/production_workflow_map.json": json.loads(map_text),
        "automation/resource_write_sets.json": json.loads(sets_text),
    }
    if args.apply:
        updated = apply_baseline_updates(ROOT, guard["path"], actual, policy, release_text, map_text, sets_text)
        print(json.dumps({"registered": True, "path": guard["path"], "previous_blob_sha": previous,
                          "new_blob_sha": actual, "approval_mode": approval_mode,
                          "config_change_commits": commits, "metadata_paths_updated": updated,
                          "repository_files_modified": True, "config_file_modified": False,
                          "config_bytes_unchanged": True}, ensure_ascii=False, sort_keys=True))
        return 0
    proposal = {"schema_version": 1, "status": "requires_watchdog_baseline_sync", "path": guard["path"],
                "previous_blob_sha": previous, "new_blob_sha": actual, "actor": owner,
                "approval_mode": approval_mode, "config_change_commits": commits,
                "proposed_updates": proposed, "repository_files_modified": False, "config_file_modified": False}
    proposal_path = write_baseline_proposal(proposal)
    print(json.dumps({"registered": False, "proposal_created": True, "proposal_path": str(proposal_path),
                      "path": guard["path"], "previous_blob_sha": previous, "new_blob_sha": actual,
                      "actor": owner, "approval_mode": approval_mode, "config_change_commits": commits,
                      "repository_files_modified": False, "config_file_modified": False},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
