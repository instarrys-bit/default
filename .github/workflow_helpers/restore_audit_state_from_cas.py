#!/usr/bin/env python3
"""Reconstruct a verified audit archive from the repository's immutable V2 CAS."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from storage.v2.artifact_store import GitHubContentsArtifactStore

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
EXPECTED_WORKFLOW_PATH = ".github/workflows/auto_sync.yml"
EXPECTED_ARTIFACT_NAME = "deterministic-audit-output"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reconstruct_archive(catalog: object, store, *, expected_run_id: str) -> bytes:
    if not isinstance(catalog, dict):
        raise ValueError("CAS catalog must be a JSON object")
    if str(catalog.get("source_run_id", "")) != str(expected_run_id):
        raise ValueError("CAS catalog run ID does not match the recorded state pointer")
    if catalog.get("source_workflow_path") != EXPECTED_WORKFLOW_PATH:
        raise ValueError("CAS catalog is not from the production audit workflow")
    if catalog.get("all_artifacts_verified") is not True:
        raise ValueError("CAS catalog does not attest that all artifacts were verified")

    matches = [
        item for item in catalog.get("artifacts", [])
        if isinstance(item, dict) and item.get("name") == EXPECTED_ARTIFACT_NAME
    ]
    if len(matches) != 1:
        raise ValueError("CAS catalog must contain exactly one deterministic audit output")
    artifact = matches[0]
    if artifact.get("verified") is not True:
        raise ValueError("deterministic audit output is not verified")

    archive_digest = artifact.get("archive_sha256")
    archive_size = artifact.get("size_in_bytes")
    segments = artifact.get("segments")
    if (not isinstance(archive_digest, str) or not SHA256_RE.fullmatch(archive_digest)
            or not isinstance(archive_size, int) or archive_size <= 0
            or archive_size > MAX_ARCHIVE_BYTES
            or not isinstance(segments, list) or not segments):
        raise ValueError("CAS artifact metadata is incomplete or outside safe limits")

    if any(not isinstance(item, dict) for item in segments):
        raise ValueError("CAS artifact contains an invalid segment record")
    ordered = sorted(segments, key=lambda item: item.get("segment_index", -1))
    if [item.get("segment_index") for item in ordered] != list(range(len(ordered))):
        raise ValueError("CAS artifact segments are missing, duplicated or out of order")

    chunks: list[bytes] = []
    total = 0
    for segment in ordered:
        record_id = segment.get("manifest_record_id")
        content_digest = segment.get("content_sha256")
        expected_size = segment.get("size_in_bytes")
        if (not isinstance(record_id, str) or not SHA256_RE.fullmatch(record_id)
                or not isinstance(content_digest, str) or not SHA256_RE.fullmatch(content_digest)
                or not isinstance(expected_size, int) or expected_size <= 0):
            raise ValueError("CAS segment metadata is invalid")
        data = store.read(record_id)
        if not isinstance(data, bytes) or len(data) != expected_size or sha256(data) != content_digest:
            raise ValueError(f"CAS segment {segment['segment_index']} failed content verification")
        chunks.append(data)
        total += len(data)
        if total > archive_size or total > MAX_ARCHIVE_BYTES:
            raise ValueError("CAS segments exceed the declared archive size")

    archive = b"".join(chunks)
    if total != archive_size or sha256(archive) != archive_digest:
        raise ValueError("reconstructed audit archive failed whole-file SHA-256 verification")
    return archive



def unwrap_artifact_payload(container: bytes) -> bytes:
    """Extract the single tar.gz file from GitHub's ZIP-wrapped artifact envelope."""
    if not container.startswith(b"PK\\x03\\x04"):
        if not container.startswith(b"\\x1f\\x8b"):
            raise ValueError("verified CAS artifact is neither a GitHub ZIP envelope nor a gzip tar archive")
        return container

    try:
        with zipfile.ZipFile(io.BytesIO(container)) as bundle:
            files = [item for item in bundle.infolist() if not item.is_dir()]
            matches = [item for item in files if item.filename == "audit-output.tar.gz"]
            if len(files) != 1 or len(matches) != 1:
                raise ValueError("GitHub artifact ZIP must contain exactly one audit-output.tar.gz file")
            item = matches[0]
            if item.file_size <= 0 or item.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("nested audit archive is empty or exceeds the safe size limit")
            payload = bundle.read(item)
    except zipfile.BadZipFile as exc:
        raise ValueError("CAS artifact has a ZIP signature but is not a valid ZIP archive") from exc

    if not payload.startswith(b"\\x1f\\x8b"):
        raise ValueError("GitHub artifact ZIP payload is not a gzip tar archive")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required for CAS reads")

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    store = GitHubContentsArtifactStore(args.repository, args.branch, token)
    container = reconstruct_archive(catalog, store, expected_run_id=args.run_id)
    archive = unwrap_artifact_payload(container)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix=args.output.name + ".", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(archive)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(args.output)
    print(json.dumps({
        "status": "verified",
        "run_id": args.run_id,
        "container_sha256": sha256(container),
        "container_size_in_bytes": len(container),
        "archive_sha256": sha256(archive),
        "size_in_bytes": len(archive),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
