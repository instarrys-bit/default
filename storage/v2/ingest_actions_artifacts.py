#!/usr/bin/env python3
"""Ingest completed GitHub Actions artifacts into Storage Management CAS.

The source artifact is deleted only after every downloaded archive has been
staged, read-back verified, and an immutable per-run catalog has been written.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO

from artifact_store import GitHubContentsArtifactStore, ArtifactConflict, canonical_bytes, sha256
from runtime import assert_automation_write_allowed

API = "https://api.github.com"
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024


def request(method: str, url: str, token: str, payload: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shadowrocket-storage-management-artifact-ingest",
    }
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and method == "GET":
            return None, ""
        if exc.code in (409, 422):
            raise ArtifactConflict(f"GitHub immutable catalog conflict ({exc.code})") from None
        detail = exc.read(500).decode("utf-8", "replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail[:300]}") from None


def get_json(url: str, token: str):
    raw, _ = request("GET", url, token)
    if raw is None:
        raise RuntimeError("GitHub API resource not found: " + url)
    return json.loads(raw.decode("utf-8"))


def load_catalog(repository: str, branch: str, token: str, run_id: int):
    path = f"storage/v2/artifacts/catalog/{run_id}.json"
    url = f"{API}/repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}?" + urllib.parse.urlencode({"ref": branch})
    raw, _ = request("GET", url, token)
    if raw is None:
        return None
    metadata = json.loads(raw.decode("utf-8"))
    encoded = metadata.get("content", "").replace("\\n", "")
    if metadata.get("encoding") != "base64" or not encoded:
        raise RuntimeError("existing artifact catalog is not readable")
    catalog = json.loads(base64.b64decode(encoded).decode("utf-8"))
    if catalog.get("source_run_id") != run_id or catalog.get("schema_version") != 1:
        raise RuntimeError("existing artifact catalog identity mismatch")
    return catalog


def put_catalog(repository: str, branch: str, token: str, run_id: int, catalog: dict):
    path = f"storage/v2/artifacts/catalog/{run_id}.json"
    assert_automation_write_allowed(path, "storage_management")
    url = f"{API}/repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}"
    raw = canonical_bytes(catalog) + b"\n"
    payload = {
        "message": f"storage: catalog Actions artifacts for run {run_id}",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": branch,
    }
    try:
        request("PUT", url, token, payload)
    except ArtifactConflict:
        existing = get_json(url + "?" + urllib.parse.urlencode({"ref": branch}), token)
        encoded = existing.get("content", "").replace("\n", "")
        current = base64.b64decode(encoded) if encoded else b""
        if current != raw:
            raise RuntimeError(f"immutable artifact catalog conflict for run {run_id}") from None


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    run_id = int(os.environ["SOURCE_RUN_ID"])
    if not token or run_id < 1:
        raise ValueError("GITHUB_TOKEN and a positive SOURCE_RUN_ID are required")

    run = get_json(f"{API}/repos/{repository}/actions/runs/{run_id}", token)
    if run.get("head_branch") != "main" or run.get("status") != "completed":
        raise RuntimeError("only completed main-branch workflow runs may be ingested")
    workflow_name = run.get("name") or run.get("path") or "unknown-workflow"
    artifacts = []
    page = 1
    while True:
        listing = get_json(
            f"{API}/repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100&page={page}",
            token,
        )
        batch = listing.get("artifacts", [])
        artifacts.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    store = GitHubContentsArtifactStore(repository, branch, token)
    existing_catalog = load_catalog(repository, branch, token, run_id)
    catalog_items = list((existing_catalog or {}).get("artifacts", []))
    already_cataloged = {int(item["artifact_id"]) for item in catalog_items}
    pending_delete = []
    for item in artifacts:
        if item.get("expired") or item.get("deleted"):
            continue
        artifact_id = int(item["id"])
        if artifact_id in already_cataloged:
            pending_delete.append(artifact_id)
            continue
        name = item.get("name") or f"artifact-{artifact_id}"
        size = int(item.get("size_in_bytes") or 0)
        if size <= 0 or size > MAX_ARCHIVE_BYTES:
            raise RuntimeError(f"artifact {artifact_id} ({name}) size {size} is outside supported bounds")
        archive, _ = request(
            "GET", f"{API}/repos/{repository}/actions/artifacts/{artifact_id}/zip", token
        )
        if archive is None or len(archive) > MAX_ARCHIVE_BYTES:
            raise RuntimeError(f"artifact {artifact_id} download is empty or exceeds 50 MiB")
        # Reject malformed archives before making a durable record.
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            bad = zipped.testzip()
            if bad is not None:
                raise RuntimeError(f"artifact {artifact_id} ZIP integrity failed at {bad}")
        provenance = {
            "source_id": f"{run_id}:{artifact_id}",
            "source_revision": run.get("head_sha") or "unknown",
            "task_id": f"github-actions-run-{run_id}",
            "producer": workflow_name,
            "source_workflow_path": run.get("path", ""),
            "source_run_id": run_id,
            "source_run_attempt": run.get("run_attempt", 1),
            "source_artifact_id": artifact_id,
            "source_artifact_name": name,
            "source_event": run.get("event", ""),
            "source_repository": repository,
            "archive_sha256": sha256(archive),
        }
        staged = store.stage(
            archive,
            artifact_type="github_actions_artifact",
            provenance=provenance,
            schema_version=1,
            producer_version="storage-management-v1",
        )
        verified = store.verify(staged["record_id"])
        if not verified.get("valid") or verified.get("content_sha256") != sha256(archive):
            raise RuntimeError(f"artifact {artifact_id} failed CAS read-back verification")
        catalog_items.append({
            "artifact_id": artifact_id,
            "name": name,
            "size_in_bytes": len(archive),
            "archive_sha256": sha256(archive),
            "cas_artifact_id": staged["artifact_id"],
            "manifest_record_id": staged["record_id"],
            "verified": True,
        })
        pending_delete.append(artifact_id)

    catalog = {
        "schema_version": 1,
        "source_run_id": run_id,
        "source_run_attempt": run.get("run_attempt", 1),
        "source_workflow": workflow_name,
        "source_workflow_path": run.get("path", ""),
        "source_commit": run.get("head_sha", ""),
        "source_branch": run.get("head_branch", ""),
        "source_event": run.get("event", ""),
        "artifacts": catalog_items,
        "all_artifacts_verified": True,
    }
    put_catalog(repository, branch, token, run_id, catalog)

    # Destructive cleanup is deliberately last and is safe to retry after a
    # partial deletion because the immutable catalog is already committed.
    for artifact_id in pending_delete:
        request("DELETE", f"{API}/repos/{repository}/actions/artifacts/{artifact_id}", token)
    print(json.dumps({
        "source_run_id": run_id,
        "catalog_path": f"storage/v2/artifacts/catalog/{run_id}.json",
        "ingested_count": len(catalog_items),
        "deleted_source_artifact_count": len(pending_delete),
        "verified": True,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"artifact-ingest: {exc}", file=sys.stderr)
        raise SystemExit(2)
