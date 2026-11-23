#!/usr/bin/env python3
"""Storage Management-owned, content-addressed repository SHA inventory.

The tracker inventories Git blob SHAs and PR head/file/review metadata. It is
read-only for source files (especially modules/uu.conf); durable writes are
limited to immutable storage/v2 artifact objects and one SHA-CAS projection.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from artifact_store import GitHubContentsArtifactStore, canonical_bytes, sha256
from queue_store import GitHubContentsJsonStore

API = "https://api.github.com"
PROJECTION = "storage/v2/projections/repository_integrity.json"
EXCLUDED_PREFIXES = ("storage/v2/artifacts/",)
EXCLUDED_EXACT = {PROJECTION}
MAX_PAGES = 100
MAX_RETRIES = 3


class IntegritySnapshotError(RuntimeError):
    pass


class GitHub:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.token = token
        self.root = f"{API}/repos/{repository}"

    def get(self, path: str, *, params: dict | None = None):
        url = path if path.startswith("https://") else self.root + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shadowrocket-file-management",
        }
        for attempt in range(MAX_RETRIES + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                    time.sleep(min(8, 2 ** attempt))
                    continue
                detail = exc.read(500).decode("utf-8", "replace")
                raise IntegritySnapshotError(f"GitHub GET {url} failed ({exc.code}): {detail[:250]}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < MAX_RETRIES:
                    time.sleep(min(8, 2 ** attempt))
                    continue
                raise IntegritySnapshotError(f"GitHub GET failed after bounded retries: {exc}") from None
        raise IntegritySnapshotError("GitHub GET retry budget exhausted")

    def pages(self, path: str, *, params: dict | None = None) -> list:
        output = []
        for page in range(1, MAX_PAGES + 1):
            query = dict(params or {})
            query.update({"per_page": 100, "page": page})
            batch = self.get(path, params=query)
            if not isinstance(batch, list):
                raise IntegritySnapshotError(f"Expected paginated array from {path}")
            output.extend(batch)
            if len(batch) < 100:
                return output
        raise IntegritySnapshotError(f"Pagination safety limit reached for {path}")

    def main_ref(self) -> str:
        ref = self.get("/git/ref/heads/main")
        sha_value = ref.get("object", {}).get("sha")
        if not isinstance(sha_value, str) or not re.fullmatch(r"[0-9a-f]{40}", sha_value):
            raise IntegritySnapshotError("main ref did not return a full commit SHA")
        return sha_value

    def tree_entries(self, commit_sha: str) -> list[dict]:
        commit = self.get(f"/git/commits/{commit_sha}")
        root_sha = commit.get("tree", {}).get("sha")
        if not isinstance(root_sha, str):
            raise IntegritySnapshotError("main commit omitted its root tree SHA")
        root = self.get(f"/git/trees/{root_sha}", params={"recursive": 1})
        if root.get("truncated") is not True:
            entries = root.get("tree", [])
            return self._normalize_tree(entries)

        # Recursive Git tree responses can be truncated. Fall back to bounded,
        # non-recursive traversal so no source paths silently disappear.
        found: list[dict] = []
        pending = [(root_sha, "")]
        seen: set[str] = set()
        while pending:
            tree_sha, prefix = pending.pop()
            if tree_sha in seen:
                continue
            seen.add(tree_sha)
            node = self.get(f"/git/trees/{tree_sha}")
            for item in node.get("tree", []):
                path = prefix + item["path"]
                if item.get("type") == "tree":
                    pending.append((item["sha"], path + "/"))
                elif item.get("type") == "blob":
                    found.append({
                        "path": path,
                        "sha": item["sha"],
                        "size": item.get("size"),
                    })
        return sorted(found, key=lambda item: item["path"])

    @staticmethod
    def _normalize_tree(entries: list[dict]) -> list[dict]:
        output = []
        for item in entries:
            if item.get("type") != "blob":
                continue
            path = item.get("path")
            blob = item.get("sha")
            if not isinstance(path, str) or not isinstance(blob, str):
                raise IntegritySnapshotError("Git tree contains a malformed blob entry")
            output.append({"path": path, "sha": blob, "size": item.get("size")})
        return sorted(output, key=lambda item: item["path"])

    def blob_bytes(self, blob_sha: str) -> bytes:
        blob = self.get(f"/git/blobs/{blob_sha}")
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise IntegritySnapshotError(f"Git blob {blob_sha} was not returned as base64")
        try:
            return base64.b64decode(blob["content"].encode("ascii"), validate=False)
        except (ValueError, UnicodeError):
            raise IntegritySnapshotError(f"Git blob {blob_sha} has invalid base64 content") from None

    def pull_inventory(self, tracked_closed: tuple[int, ...] = (504,)) -> list[dict]:
        pulls = self.pages("/pulls", params={"state": "open", "sort": "updated", "direction": "desc"})
        by_number = {int(item["number"]): item for item in pulls}
        for number in tracked_closed:
            if number not in by_number:
                item = self.get(f"/pulls/{number}")
                by_number[number] = item
        output = []
        for number, pr in sorted(by_number.items()):
            files = self.pages(f"/pulls/{number}/files")
            reviews = self.pages(f"/pulls/{number}/reviews")
            review_comments = self.pages(f"/pulls/{number}/comments")
            output.append({
                "number": number,
                "state": pr.get("state"),
                "merged": pr.get("merged"),
                "merged_at": pr.get("merged_at"),
                "head_ref": pr.get("head", {}).get("ref"),
                "head_sha": pr.get("head", {}).get("sha"),
                "base_ref": pr.get("base", {}).get("ref"),
                "base_sha": pr.get("base", {}).get("sha"),
                "changed_files": [
                    {
                        "path": item.get("filename"),
                        "blob_sha": item.get("sha"),
                        "status": item.get("status"),
                    }
                    for item in files
                ],
                "reviews": [
                    {
                        "id": item.get("id"),
                        "state": item.get("state"),
                        "commit_id": item.get("commit_id"),
                        "submitted_at": item.get("submitted_at"),
                    }
                    for item in reviews
                ],
                "review_comments": [
                    {
                        "id": item.get("id"),
                        "path": item.get("path"),
                        "commit_id": item.get("commit_id"),
                        "original_commit_id": item.get("original_commit_id"),
                        "created_at": item.get("created_at"),
                    }
                    for item in review_comments
                ],
            })
        return output


def source_entries(entries: list[dict]) -> list[dict]:
    return [
        item for item in entries
        if item["path"] not in EXCLUDED_EXACT
        and not item["path"].startswith(EXCLUDED_PREFIXES)
    ]


def normalized_pull_inventory(pulls: list[dict]) -> list[dict]:
    normalized = []
    for pr in pulls:
        item = dict(pr)
        # A Storage Management commit advances main and therefore the base SHA
        # of every main-target PR. Do not let that create a self-trigger loop.
        if item.get("base_ref") == "main":
            item["base_sha"] = "<main-base-normalized>"
        normalized.append(item)
    return normalized


def inventory_digest(entries: list[dict], pulls: list[dict]) -> str:
    payload = {
        "files": source_entries(entries),
        "pull_requests": normalized_pull_inventory(pulls),
    }
    return sha256(canonical_bytes(payload))


def protected_config_record(client: GitHub, entries: list[dict]) -> dict:
    item = next((x for x in entries if x["path"] == "modules/uu.conf"), None)
    if item is None:
        raise IntegritySnapshotError("protected modules/uu.conf is missing from main tree")
    data = client.blob_bytes(item["sha"])
    return {
        "path": "modules/uu.conf",
        "git_blob_sha": item["sha"],
        "sha256": sha256(data),
        "size_bytes": len(data),
        "access": "read_only",
    }


def pointer_store(repository: str, token: str, bootstrap: Path) -> GitHubContentsJsonStore:
    bootstrap.write_text(json.dumps({
        "schema_version": 1,
        "revision": 0,
        "latest_snapshot": None,
    }, sort_keys=True) + "\n", encoding="utf-8")
    return GitHubContentsJsonStore(
        repository,
        path=PROJECTION,
        branch="main",
        token=token,
        bootstrap_path=bootstrap,
    )


def _run_once(repository: str, token: str) -> dict:
    client = GitHub(repository, token)
    source_main_sha = client.main_ref()
    entries = client.tree_entries(source_main_sha)
    config_before = protected_config_record(client, entries)
    pulls = client.pull_inventory()
    digest = inventory_digest(entries, pulls)
    snapshot = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_main_sha": source_main_sha,
        "source_tree_digest": sha256(canonical_bytes(source_entries(entries))),
        "inventory_digest": digest,
        "file_count": len(source_entries(entries)),
        "pull_request_count": len(pulls),
        "files": source_entries(entries),
        "pull_requests": pulls,
        "protected_config": config_before,
        "write_policy": {
            "production_publish_scope": "rulesets/**",
            "protected_config_write_scope": [],
            "tracker_write_scope": [
                "storage/v2/artifacts/sha256/<digest>",
                PROJECTION,
            ],
        },
    }
    data = canonical_bytes(snapshot) + b"\n"

    with TemporaryDirectory(prefix="repository-integrity-") as temp:
        store = pointer_store(repository, token, Path(temp) / "bootstrap.json")
        current = store.read().document
        latest = current.get("latest_snapshot") or {}
        if latest.get("inventory_digest") == digest:
            # No-op runs still re-read the protected blob and the source tree.
            final_sha = client.main_ref()
            final_entries = client.tree_entries(final_sha)
            config_after = protected_config_record(client, final_entries)
            if config_after["git_blob_sha"] != config_before["git_blob_sha"]:
                raise IntegritySnapshotError("uu.conf Git blob SHA changed during no-op verification")
            if sha256(canonical_bytes(source_entries(final_entries))) != snapshot["source_tree_digest"]:
                raise IntegritySnapshotError("source tree changed during no-op verification")
            final_pulls = client.pull_inventory()
            if inventory_digest(final_entries, final_pulls) != digest:
                raise IntegritySnapshotError("PR heads, changed files or review metadata changed during no-op verification")
            return {
                "status": "unchanged",
                "inventory_digest": digest,
                "source_main_sha": source_main_sha,
                "final_main_sha": final_sha,
                "uu_conf_blob_sha": config_after["git_blob_sha"],
                "file_count": snapshot["file_count"],
                "pull_request_count": len(pulls),
            }

        # Verify no source drift immediately before staging immutable bytes.
        before_stage_sha = client.main_ref()
        before_stage_entries = client.tree_entries(before_stage_sha)
        before_stage_config = protected_config_record(client, before_stage_entries)
        if before_stage_config["git_blob_sha"] != config_before["git_blob_sha"]:
            raise IntegritySnapshotError("uu.conf changed before snapshot staging")
        if sha256(canonical_bytes(source_entries(before_stage_entries))) != snapshot["source_tree_digest"]:
            raise IntegritySnapshotError("source tree changed before snapshot staging")
        before_stage_pulls = client.pull_inventory()
        if inventory_digest(before_stage_entries, before_stage_pulls) != digest:
            raise IntegritySnapshotError("PR heads, changed files or review metadata changed before snapshot staging")

        artifacts = GitHubContentsArtifactStore(repository, "main", token)
        artifact = artifacts.stage(
            data,
            artifact_type="repository_integrity_snapshot",
            provenance={
                "source_id": f"github:{repository}",
                "source_revision": source_main_sha,
                "task_id": "repository-integrity:" + digest[:24],
                "producer": "storage_management",
            },
            schema_version=1,
            producer_version="repository-integrity/1",
        )

        # Artifact commits are excluded from the source digest. Confirm that
        # neither the source tree nor uu.conf changed before moving the pointer.
        after_artifact_sha = client.main_ref()
        after_artifact_entries = client.tree_entries(after_artifact_sha)
        after_artifact_config = protected_config_record(client, after_artifact_entries)
        if after_artifact_config["git_blob_sha"] != config_before["git_blob_sha"]:
            raise IntegritySnapshotError("uu.conf changed during artifact staging")
        if sha256(canonical_bytes(source_entries(after_artifact_entries))) != snapshot["source_tree_digest"]:
            raise IntegritySnapshotError("source tree changed during artifact staging")
        after_artifact_pulls = client.pull_inventory()
        if inventory_digest(after_artifact_entries, after_artifact_pulls) != digest:
            raise IntegritySnapshotError("PR heads, changed files or review metadata changed during artifact staging")

        def update_pointer(document: dict):
            latest_value = document.get("latest_snapshot") or {}
            if latest_value.get("inventory_digest") == digest:
                return document, {"status": "already_current"}
            document["revision"] = int(document.get("revision", 0)) + 1
            document["latest_snapshot"] = {
                "inventory_digest": digest,
                "artifact_record_id": artifact["record_id"],
                "artifact_content_sha256": artifact["content_sha256"],
                "source_main_sha": source_main_sha,
                "source_tree_digest": snapshot["source_tree_digest"],
                "uu_conf_git_blob_sha": config_before["git_blob_sha"],
                "uu_conf_sha256": config_before["sha256"],
                "file_count": snapshot["file_count"],
                "pull_request_count": len(pulls),
                "captured_at": snapshot["captured_at"],
            }
            return document, {"status": "updated", "revision": document["revision"]}

        result = store.mutate(update_pointer, max_conflicts=5)
        readback = store.read().document
        latest_readback = readback.get("latest_snapshot") or {}
        if latest_readback.get("inventory_digest") != digest:
            raise IntegritySnapshotError("repository integrity pointer read-back mismatch")

        final_sha = client.main_ref()
        final_entries = client.tree_entries(final_sha)
        config_after = protected_config_record(client, final_entries)
        if config_after["git_blob_sha"] != config_before["git_blob_sha"]:
            raise IntegritySnapshotError("uu.conf Git blob SHA changed after snapshot")
        if sha256(canonical_bytes(source_entries(final_entries))) != snapshot["source_tree_digest"]:
            raise IntegritySnapshotError("source tree changed after snapshot")
        final_pulls = client.pull_inventory()
        if inventory_digest(final_entries, final_pulls) != digest:
            raise IntegritySnapshotError("PR heads, changed files or review metadata changed after snapshot")
        return {
            "status": result["status"],
            "revision": readback["revision"],
            "inventory_digest": digest,
            "artifact_record_id": artifact["record_id"],
            "artifact_content_sha256": artifact["content_sha256"],
            "source_main_sha": source_main_sha,
            "final_main_sha": final_sha,
            "uu_conf_blob_sha": config_after["git_blob_sha"],
            "file_count": snapshot["file_count"],
            "pull_request_count": len(pulls),
        }



MAX_SNAPSHOT_ATTEMPTS = 3
SNAPSHOT_DRIFT_RETRY_MARKERS = (
    "source tree changed",
    "PR heads, changed files or review metadata changed",
)


def run(repository: str, token: str) -> dict:
    """Retry bounded snapshots when concurrent repository writes invalidate one.

    The captured source commit is immutable. A concurrent main-branch update can
    invalidate the final freshness check without making the captured snapshot
    corrupt. Re-capture a fresh point-in-time snapshot a bounded number of times;
    never retry protected-config drift or unrelated integrity failures.
    """
    for attempt in range(1, MAX_SNAPSHOT_ATTEMPTS + 1):
        try:
            return _run_once(repository, token)
        except IntegritySnapshotError as exc:
            message = str(exc)
            retryable = any(marker in message for marker in SNAPSHOT_DRIFT_RETRY_MARKERS)
            if not retryable or attempt >= MAX_SNAPSHOT_ATTEMPTS:
                raise
            delay = min(4, 2 ** (attempt - 1))
            print(json.dumps({
                "status": "retrying",
                "attempt": attempt,
                "max_attempts": MAX_SNAPSHOT_ATTEMPTS,
                "retry_in_seconds": delay,
                "reason": message,
            }, ensure_ascii=False, sort_keys=True), flush=True)
            time.sleep(delay)
    raise IntegritySnapshotError("repository integrity snapshot retry budget exhausted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()
    try:
        result = run(args.repository, args.token)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
