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
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO

from artifact_store import GitHubContentsArtifactStore, ArtifactConflict, canonical_bytes, sha256
from runtime import assert_automation_write_allowed

API = "https://api.github.com"
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_SEGMENT_BYTES = 48 * 1024 * 1024
MAX_RUNS_PER_SCAN = 30


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


def download_artifact_zip(url: str, token: str):
    """Download the GitHub redirect target without forwarding the API bearer token."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shadowrocket-storage-management-artifact-ingest",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, file_pointer, code, message, response_headers, new_url):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=90) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            detail = exc.read(500).decode("utf-8", "replace")
            raise RuntimeError(f"GitHub artifact download HTTP {exc.code}: {detail[:300]}") from None
        location = exc.headers.get("Location")
        parsed = urllib.parse.urlparse(location or "")
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError("GitHub artifact download returned an invalid redirect URL") from None
        # Deliberately omit Authorization on the signed blob-storage URL.
        redirected = urllib.request.Request(
            location, headers={"User-Agent": "shadowrocket-storage-management-artifact-ingest"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(redirected, timeout=90) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as blob_error:
            detail = blob_error.read(500).decode("utf-8", "replace")
            raise RuntimeError(f"artifact blob download HTTP {blob_error.code}: {detail[:300]}") from None


def load_catalog(repository: str, branch: str, token: str, run_id: int):
    path = f"storage/v2/artifacts/catalog/{run_id}.json"
    url = f"{API}/repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}?" + urllib.parse.urlencode({"ref": branch})
    raw, _ = request("GET", url, token)
    if raw is None:
        return None
    metadata = json.loads(raw.decode("utf-8"))
    encoded = metadata.get("content", "").replace("\n", "")
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


def scan_recent_runs(repository: str, token: str) -> int:
    """Poll recent repository artifacts because GITHUB_TOKEN completions may not emit workflow_run."""
    import datetime
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)
    run_ids = set()
    for page in range(1, 21):
        listing = get_json(
            f"{API}/repos/{repository}/actions/artifacts?per_page=100&page={page}",
            token,
        )
        batch = listing.get("artifacts", [])
        if not batch:
            break
        for artifact in batch:
            if artifact.get("expired") or artifact.get("deleted"):
                continue
            source = artifact.get("workflow_run") or {}
            if source.get("head_branch") != "main" or not source.get("id"):
                continue
            created = artifact.get("created_at")
            if created:
                stamp = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
                if stamp < cutoff:
                    continue
            run_ids.add(int(source["id"]))
        oldest = batch[-1].get("created_at")
        if oldest:
            stamp = datetime.datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            if stamp < cutoff:
                break

    failures = []
    processed = 0
    ordered_run_ids = sorted(run_ids)
    eligible_runs = []
    for source_run_id in ordered_run_ids:
        run = get_json(f"{API}/repos/{repository}/actions/runs/{source_run_id}", token)
        path = run.get("path", "")
        if run.get("status") != "completed" or run.get("head_branch") != "main":
            continue
        if path not in {
            ".github/workflows/auto_sync.yml",
            ".github/workflows/automation-watchdog.yml",
        }:
            continue
        eligible_runs.append(source_run_id)

    selected_run_ids = eligible_runs[:MAX_RUNS_PER_SCAN]
    deferred_run_count = max(0, len(eligible_runs) - len(selected_run_ids))
    for source_run_id in selected_run_ids:
        env = os.environ.copy()
        env["SOURCE_RUN_ID"] = str(source_run_id)
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            env=env, capture_output=True, text=True, check=False,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode:
            failures.append(source_run_id)
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)
            if "GitHub API HTTP 401" in result.stderr or "GitHub API HTTP 403" in result.stderr:
                print("artifact-ingest: stopping scan after systemic GitHub authentication/permission failure", file=sys.stderr)
                break
        else:
            processed += 1
    print(json.dumps({
        "scan_mode": "recent_repository_artifacts",
        "candidate_run_count": len(run_ids),
        "eligible_run_count": len(eligible_runs),
        "selected_run_count": len(selected_run_ids),
        "processed_run_count": processed,
        "deferred_run_count": deferred_run_count,
        "failed_run_ids": failures,
        "lookback_days": 90,
    }, ensure_ascii=False))
    return 1 if failures else 0


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if not token:
        raise ValueError("GITHUB_TOKEN is required")
    if sys.argv[1:] == ["--scan-recent"]:
        return scan_recent_runs(repository, token)
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

    if not artifacts:
        print(json.dumps({
            "source_run_id": run_id,
            "ingested_count": 0,
            "deleted_source_artifact_count": 0,
            "skipped": "source run has no remaining artifacts",
        }, ensure_ascii=False))
        return 0

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
        archive, _ = download_artifact_zip(
            f"{API}/repos/{repository}/actions/artifacts/{artifact_id}/zip", token
        )
        if archive is None or len(archive) > MAX_ARCHIVE_BYTES:
            raise RuntimeError(f"artifact {artifact_id} download is empty or exceeds 250 MiB")
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
        segment_records = []
        segment_count = (len(archive) + MAX_SEGMENT_BYTES - 1) // MAX_SEGMENT_BYTES
        for segment_index in range(segment_count):
            segment = archive[segment_index * MAX_SEGMENT_BYTES:(segment_index + 1) * MAX_SEGMENT_BYTES]
            segment_provenance = {
                **provenance,
                "source_id": f"{run_id}:{artifact_id}:{segment_index}",
                "segment_index": segment_index,
                "segment_count": segment_count,
            }
            staged = store.stage(
                segment,
                artifact_type="github_actions_artifact",
                provenance=segment_provenance,
                schema_version=1,
                producer_version="storage-management-v1",
            )
            verified = store.verify(staged["record_id"])
            if not verified.get("valid") or verified.get("content_sha256") != sha256(segment):
                raise RuntimeError(f"artifact {artifact_id} segment {segment_index} failed CAS read-back verification")
            segment_records.append({
                "segment_index": segment_index,
                "size_in_bytes": len(segment),
                "content_sha256": sha256(segment),
                "cas_artifact_id": staged["artifact_id"],
                "manifest_record_id": staged["record_id"],
            })
        catalog_items.append({
            "artifact_id": artifact_id,
            "name": name,
            "size_in_bytes": len(archive),
            "archive_sha256": sha256(archive),
            "segment_count": segment_count,
            "segments": segment_records,
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
