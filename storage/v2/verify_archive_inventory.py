#!/usr/bin/env python3
"""Verify the frozen V1 inventory against the actual GitHub archive tree."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import verify_archive_tree_inventory, validate_migration_manifest


def github_get(url: str, token: str | None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "v1-archive-integrity-verifier",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"GitHub archive verification request failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "instarrys-bit/default"))
    parser.add_argument("--inventory", default=str(ROOT / "docs/v2/legacy-v1-inventory.json"))
    parser.add_argument("--manifest", default=str(ROOT / "storage/v2/migration/v1-source-manifest.json"))
    args = parser.parse_args()
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    validate_migration_manifest(manifest, inventory)
    archive = manifest["source_archive"]
    api = "https://api.github.com/repos/" + args.repository
    commit = github_get(api + "/git/commits/" + archive["commit"], os.environ.get("GITHUB_TOKEN"))
    actual_tree_sha = commit.get("tree", {}).get("sha")
    if actual_tree_sha != archive["tree_sha"]:
        raise ValueError(
            "archive commit tree SHA mismatch: "
            f"manifest={archive['tree_sha']} actual={actual_tree_sha}"
        )
    tree = github_get(api + "/git/trees/" + actual_tree_sha + "?recursive=1", os.environ.get("GITHUB_TOKEN"))
    report = verify_archive_tree_inventory(inventory, tree)
    report.update({
        "repository": args.repository,
        "archive_branch": archive["branch"],
        "archive_commit": archive["commit"],
        "inventory_path": archive["inventory_path"],
        "migration_entry_count": len(manifest["entries"]),
        "migration_entries_imported": False,
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"archive-integrity: {exc}", file=sys.stderr)
        raise SystemExit(2)
