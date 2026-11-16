"""Verified bridge from the existing V1 Discovery/Assessment artifacts into V2 CAS.

Validation is read-only by default. Durable staging requires an explicit execute
flag, a matching initialized V2 epoch, and the Storage Management token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts"))

DISCOVERY_WORKFLOW = "Shadowrocket Source Discovery (Watchdog)"
ASSESSMENT_WORKFLOW_PATH = ".github/workflows/automation-watchdog.yml"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_FILES = 5000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 200 * 1024 * 1024


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path contains an unsafe segment")
    return path.as_posix()


def _unique_proof(root: Path, name: str) -> tuple[Path, dict]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("artifact root must be an existing non-symlink directory")
    hits = [path for path in root.rglob(name) if path.is_file() and not path.is_symlink()]
    if len(hits) != 1:
        raise ValueError("expected exactly one " + name)
    try:
        value = json.loads(hits[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(name + " is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(name + " must contain a JSON object")
    return hits[0], value


def _logical_document_digest(root: Path, relative: str) -> str:
    """Match task_scheduler.read_only_resource_digests for this exact document."""
    path = root / _safe_relative(relative)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Discovery logical document is not a regular file")
    digest = hashlib.sha256()
    found = False
    if path.is_file():
        digest.update(b"legacy-json\0")
        digest.update(path.read_bytes())
        found = True
    manifest_path = path.with_name(path.name + ".manifest.json")
    if manifest_path.is_symlink():
        raise ValueError("Discovery document manifest cannot be a symlink")
    if manifest_path.is_file():
        raw_manifest = manifest_path.read_bytes()
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Discovery document manifest is invalid") from exc
        if not isinstance(manifest, dict):
            raise ValueError("Discovery document manifest must be an object")
        directory = manifest.get("shard_directory")
        shards = manifest.get("shards")
        if (manifest.get("logical_path") != path.name or not isinstance(directory, str)
                or PurePosixPath(directory).name != directory
                or directory in {"", ".", ".."} or not isinstance(shards, list)):
            raise ValueError("Discovery document manifest identity is invalid")
        digest.update(b"manifest\0")
        digest.update(raw_manifest)
        for item in shards:
            name = item.get("file") if isinstance(item, dict) else None
            if (not isinstance(name, str) or PurePosixPath(name).name != name
                    or not name.endswith(".jsonl") or name in {"", ".", ".."}):
                raise ValueError("Discovery shard manifest entry is invalid")
            shard = manifest_path.parent / directory / name
            if shard.is_symlink() or not shard.is_file():
                raise ValueError("Discovery document shard is missing or unsafe: " + name)
            digest.update(name.encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(shard.read_bytes()).digest())
        found = True
    if not found:
        raise ValueError("Discovery logical document is missing")
    return digest.hexdigest()


def _collect_files(root: Path) -> list[dict]:
    files = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in artifact tree: " + str(path.relative_to(root)))
        if not path.is_file():
            continue
        relative = _safe_relative(path.relative_to(root).as_posix())
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError("artifact file exceeds 50 MiB: " + relative)
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("artifact tree exceeds 200 MiB")
        files.append({"path": relative, "content": path.read_bytes(), "size_bytes": size})
        if len(files) > MAX_FILES:
            raise ValueError("artifact tree exceeds 5,000 files")
    if not files:
        raise ValueError("artifact tree is empty")
    return files


def validate_handoff(*, discovery_root: str | Path, assessment_root: str | Path,
                     assessment_task_id: str, discovery_run_id: str,
                     discovery_head_sha: str, assessment_run_id: str,
                     assessment_head_sha: str) -> dict:
    """Verify exact Discovery predecessor and independently verified Assessment proof."""
    discovery_root = Path(discovery_root).resolve()
    assessment_root = Path(assessment_root).resolve()
    if not assessment_task_id or not assessment_task_id.startswith("task_"):
        raise ValueError("assessment_task_id must be a canonical Watchdog task ID")
    if not str(discovery_run_id).isdigit() or int(discovery_run_id) <= 0:
        raise ValueError("discovery_run_id must be a positive workflow run ID")
    if not str(assessment_run_id).isdigit() or int(assessment_run_id) <= 0:
        raise ValueError("assessment_run_id must be a positive workflow run ID")
    if not SHA1_RE.fullmatch(discovery_head_sha) or not SHA1_RE.fullmatch(assessment_head_sha):
        raise ValueError("workflow head SHAs must be 40-character Git commit SHAs")

    discovery_proof_path, discovery_proof = _unique_proof(discovery_root, "source-discovery-proof.json")
    discovery_expected = {
        "workflow_name": DISCOVERY_WORKFLOW,
        "workflow_run_id": str(discovery_run_id),
        "workflow_head_sha": discovery_head_sha,
        "artifact_path": "sources/discovered_sources.json",
    }
    for key, expected in discovery_expected.items():
        if discovery_proof.get(key) != expected:
            raise ValueError("Discovery proof mismatch: " + key)
    actual_discovery_digest = _logical_document_digest(discovery_root, "sources/discovered_sources.json")
    if discovery_proof.get("artifact_sha256") != actual_discovery_digest:
        raise ValueError("Discovery logical-document digest does not match its proof")
    discovery_doc = discovery_root / "sources" / "discovered_sources.json"
    from json_document_store import read_document
    try:
        document = read_document(discovery_doc, "candidates", {"candidates": []})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Discovery source document or shard set is invalid") from exc
    if document.get("producer") != {
        "workflow_name": DISCOVERY_WORKFLOW,
        "workflow_run_id": str(discovery_run_id),
        "workflow_head_sha": discovery_head_sha,
    }:
        raise ValueError("Discovery document producer identity mismatch")

    assessment_proof_path, assessment_proof = _unique_proof(assessment_root, "source-assessment-proof.json")
    if assessment_proof.get("schema_version") != 1:
        raise ValueError("unsupported Assessment proof schema")
    if assessment_proof.get("assessment_task_id") != assessment_task_id:
        raise ValueError("Assessment task identity mismatch")
    if assessment_proof.get("task_status") != "SUCCEEDED" or assessment_proof.get("verification_status") != "passed":
        raise ValueError("Assessment task is not independently verified SUCCEEDED")
    verification = assessment_proof.get("artifact_verification")
    if not isinstance(verification, dict) or verification.get("valid") is not True or verification.get("activation_count") != 0:
        raise ValueError("Assessment artifact does not prove non-activation")
    predecessor = assessment_proof.get("predecessor")
    expected_predecessor = {
        "program_id": "script_discover_sources",
        "workflow_name": DISCOVERY_WORKFLOW,
        "workflow_run_id": str(discovery_run_id),
        "workflow_head_sha": discovery_head_sha,
        "artifact_path": "sources/discovered_sources.json",
        "artifact_sha256": actual_discovery_digest,
    }
    if predecessor != expected_predecessor:
        raise ValueError("Assessment predecessor does not match the verified Discovery artifact")
    if assessment_proof.get("producer_workflow_path") != ASSESSMENT_WORKFLOW_PATH:
        raise ValueError("Assessment producer workflow path mismatch")
    if str(assessment_proof.get("producer_workflow_run_id")) != str(assessment_run_id):
        raise ValueError("Assessment producer workflow run ID mismatch")
    if assessment_proof.get("producer_workflow_head_sha") != assessment_head_sha:
        raise ValueError("Assessment producer workflow head SHA mismatch")

    declared = assessment_proof.get("files")
    if not isinstance(declared, list) or not declared:
        raise ValueError("Assessment proof file manifest is empty")
    declared_map = {}
    for row in declared:
        if not isinstance(row, dict):
            raise ValueError("Assessment file manifest row is invalid")
        relative = _safe_relative(row.get("path"))
        digest = row.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest) or relative == "source-assessment-proof.json":
            raise ValueError("Assessment file manifest entry is invalid")
        if relative in declared_map:
            raise ValueError("Assessment file manifest contains duplicate paths")
        declared_map[relative] = digest
    assessment_files = _collect_files(assessment_root)
    actual_map = {item["path"]: hashlib.sha256(item["content"]).hexdigest()
                  for item in assessment_files if item["path"] != "source-assessment-proof.json"}
    if actual_map != declared_map:
        raise ValueError("Assessment artifact file set or SHA-256 differs from its proof")
    manifest_digest = hashlib.sha256(
        json.dumps(declared, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if assessment_proof.get("artifact_sha256") != manifest_digest:
        raise ValueError("Assessment manifest digest mismatch")
    if "source-assessment-proof.json" not in {item["path"] for item in assessment_files}:
        raise ValueError("Assessment proof file is missing from the artifact tree")

    discovery_files = _collect_files(discovery_root)
    return {
        "schema_version": 1,
        "assessment_task_id": assessment_task_id,
        "discovery": {
            **discovery_expected,
            "artifact_sha256": actual_discovery_digest,
            "proof_sha256": hashlib.sha256(discovery_proof_path.read_bytes()).hexdigest(),
        },
        "assessment": {
            "workflow_run_id": str(assessment_run_id),
            "workflow_head_sha": assessment_head_sha,
            "proof_sha256": hashlib.sha256(assessment_proof_path.read_bytes()).hexdigest(),
            "artifact_sha256": manifest_digest,
        },
        "discovery_files": discovery_files,
        "assessment_files": assessment_files,
        "file_count": len(discovery_files) + len(assessment_files),
        "total_bytes": sum(x["size_bytes"] for x in discovery_files + assessment_files),
    }


def stage_validated_handoff(validated: dict, store) -> dict:
    """Stage each exact source file, then publish one immutable handoff manifest."""
    task_id = validated["assessment_task_id"]
    staged = []
    for stage_name, key in (("discovery", "discovery_files"), ("assessment", "assessment_files")):
        proof = validated[stage_name]
        run_id = proof["workflow_run_id"]
        revision = proof.get("workflow_head_sha") or validated["assessment"]["workflow_head_sha"]
        for item in validated[key]:
            relative = item["path"]
            provenance = {
                "source_id": f"actions-run:{run_id}/{relative}",
                "source_revision": revision,
                "task_id": task_id if stage_name == "assessment" else "discovery-run-" + run_id,
                "producer": "v2-production-handoff-ingest",
            }
            artifact = store.stage(
                item["content"],
                artifact_type=stage_name + "_file",
                provenance=provenance,
                schema_version=1,
                producer_version="v2-source-handoff/1",
            )
            staged.append({
                "stage": stage_name,
                "path": relative,
                "artifact_id": artifact["artifact_id"],
                "record_id": artifact["record_id"],
                "content_sha256": artifact["content_sha256"],
                "size_bytes": artifact["size_bytes"],
            })
    handoff_manifest = {
        "schema_version": 1,
        "handoff_type": "verified_v1_discovery_assessment",
        "assessment_task_id": task_id,
        "discovery": validated["discovery"],
        "assessment": validated["assessment"],
        "staged_artifacts": staged,
        "file_count": len(staged),
        "total_bytes": validated["total_bytes"],
        "activation_count": 0,
        "publication_status": "NOT_PUBLISHED",
    }
    manifest_artifact = store.stage(
        json.dumps(handoff_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        artifact_type="source_handoff",
        provenance={
            "source_id": "source-handoff:" + task_id,
            "source_revision": validated["assessment"]["workflow_head_sha"],
            "task_id": task_id,
            "producer": "v2-production-handoff-ingest",
        },
        schema_version=1,
        producer_version="v2-source-handoff/1",
    )
    return {
        "handoff_artifact_id": manifest_artifact["artifact_id"],
        "handoff_record_id": manifest_artifact["record_id"],
        "file_artifact_count": len(staged),
        "file_count": len(staged),
        "total_bytes": validated["total_bytes"],
        "activation_count": 0,
        "publication_status": "NOT_PUBLISHED",
        "staged_artifacts": staged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-root", default=os.environ.get("AUTOMATION_SOURCE_DISCOVERY_ROOT"))
    parser.add_argument("--assessment-root", default=os.environ.get("AUTOMATION_SOURCE_ASSESSMENT_ROOT"))
    parser.add_argument("--assessment-task-id", default=os.environ.get("AUTOMATION_SOURCE_ASSESSMENT_TASK_ID"))
    parser.add_argument("--discovery-run-id", default=os.environ.get("AUTOMATION_SOURCE_DISCOVERY_RUN_ID"))
    parser.add_argument("--discovery-head-sha", default=os.environ.get("AUTOMATION_SOURCE_DISCOVERY_HEAD_SHA"))
    parser.add_argument("--assessment-run-id", default=os.environ.get("AUTOMATION_SOURCE_ASSESSMENT_RUN_ID"))
    parser.add_argument("--assessment-head-sha", default=os.environ.get("AUTOMATION_SOURCE_ASSESSMENT_HEAD_SHA"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--execute", action="store_true", help="write only after V2 epoch and Storage Management token checks")
    args = parser.parse_args()
    required = (args.discovery_root, args.assessment_root, args.assessment_task_id,
                args.discovery_run_id, args.discovery_head_sha, args.assessment_run_id,
                args.assessment_head_sha)
    if not args.discovery_root or not args.assessment_root:
        raise SystemExit("verified Discovery/Assessment artifact roots are required")
    if not args.discovery_head_sha or not args.assessment_head_sha:
        _, discovery_proof = _unique_proof(Path(args.discovery_root).resolve(), "source-discovery-proof.json")
        _, assessment_proof = _unique_proof(Path(args.assessment_root).resolve(), "source-assessment-proof.json")
        args.discovery_head_sha = args.discovery_head_sha or discovery_proof.get("workflow_head_sha")
        args.assessment_head_sha = args.assessment_head_sha or assessment_proof.get("producer_workflow_head_sha")
        args.discovery_run_id = args.discovery_run_id or discovery_proof.get("workflow_run_id")
        args.assessment_run_id = args.assessment_run_id or str(assessment_proof.get("producer_workflow_run_id", ""))
        args.assessment_task_id = args.assessment_task_id or assessment_proof.get("assessment_task_id")
    required = (args.assessment_task_id, args.discovery_run_id, args.discovery_head_sha,
                args.assessment_run_id, args.assessment_head_sha)
    if any(not value for value in required):
        raise SystemExit("verified Discovery/Assessment provenance identifiers are required")
    validated = validate_handoff(
        discovery_root=args.discovery_root,
        assessment_root=args.assessment_root,
        assessment_task_id=args.assessment_task_id,
        discovery_run_id=args.discovery_run_id,
        discovery_head_sha=args.discovery_head_sha,
        assessment_run_id=args.assessment_run_id,
        assessment_head_sha=args.assessment_head_sha,
    )
    if not args.execute:
        print(json.dumps({
            "valid": True, "dry_run": True, "assessment_task_id": validated["assessment_task_id"],
            "file_count": validated["file_count"], "total_bytes": validated["total_bytes"],
            "activation_count": 0, "publication_status": "NOT_PUBLISHED",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    token = os.environ.get("STORAGE_MANAGEMENT_TOKEN")
    epoch_id = os.environ.get("V2_STORAGE_EPOCH_ID")
    if not token or not epoch_id or not args.repository:
        raise SystemExit("--execute requires STORAGE_MANAGEMENT_TOKEN, V2_STORAGE_EPOCH_ID and repository")
    from runtime import GitHubContentsBackend, project
    state_backend = GitHubContentsBackend(args.repository, args.branch, token)
    state, _ = state_backend.read()
    if state is None or state.get("epoch_id") != epoch_id:
        raise SystemExit("V2 storage epoch is not initialized or does not match the approved epoch ID")
    project(state)
    from artifact_store import GitHubContentsArtifactStore
    store = GitHubContentsArtifactStore(args.repository, args.branch, token)
    result = stage_validated_handoff(validated, store)
    print(json.dumps({"valid": True, "dry_run": False, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
