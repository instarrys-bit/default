#!/usr/bin/env python3
"""Persist every discovered repository and rule-list file as a non-activating registry."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from json_document_store import manifest_path, read_document, write_document
from resource_lease_runtime import assert_resource_lease_from_environment

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "rulesets/source_candidate_registry.json"
REGISTRY_SCHEMA = 1
MAX_REGISTRY_BYTES = 40_000_000
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SENSITIVE_PATH_RE = re.compile(r"(?:porn|adult|nsfw|xxx|sex[-_]?content)", re.I)


def source_id_for(repository: str, url: str) -> str:
    key = repository.casefold() + "\n" + url
    return "src_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _validate_rule_url(repository: str, value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment):
        raise ValueError("discovered rule-list URL must be a clean HTTPS raw.githubusercontent.com URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or "/".join(parts[:2]).casefold() != repository.casefold():
        raise ValueError("discovered rule-list URL does not belong to its repository")
    if SENSITIVE_PATH_RE.search(parsed.path):
        raise ValueError("sensitive rule-list paths are excluded from the candidate registry")
    return parsed.path, Path(parts[-1]).suffix.lower().lstrip(".")


def build_registry(existing: dict, discovery: dict, provenance: dict, now: str) -> dict:
    if not isinstance(existing, dict):
        raise ValueError("existing source candidate registry must be an object")
    if existing and existing.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError("existing source candidate registry schema is unsupported")
    repositories = {
        str(item.get("repository", "")).casefold(): dict(item)
        for item in existing.get("repositories", [])
        if isinstance(item, dict) and item.get("repository")
    }
    source_files = {
        str(item.get("source_id", "")): dict(item)
        for item in existing.get("source_files", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    run_id = str(provenance.get("workflow_run_id", ""))
    if not run_id.isdigit():
        raise ValueError("discovery provenance must contain a numeric workflow run ID")
    if not re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("workflow_head_sha", ""))):
        raise ValueError("discovery provenance must contain a full workflow head SHA")
    artifact_sha = str(provenance.get("artifact_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha):
        raise ValueError("discovery provenance must contain an artifact SHA-256 digest")

    for item in repositories.values():
        item["present_in_latest_discovery_inventory"] = False
    for item in source_files.values():
        item["present_in_latest_discovery_inventory"] = False

    candidates = discovery.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("discovery artifact candidates must be an array")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("discovery candidates must be objects")
        repository = str(candidate.get("repository", "")).strip()
        if not REPOSITORY_RE.fullmatch(repository):
            raise ValueError("discovered repository identity is invalid")
        repo_key = repository.casefold()
        old_repo = repositories.get(repo_key, {})
        is_new_run = old_repo.get("last_seen_run_id") != run_id
        discovered_at = str(candidate.get("discovered_at") or now)
        urls = candidate.get("rule_list_urls", [])
        if not isinstance(urls, list):
            raise ValueError("rule_list_urls must be an array")
        unique_urls = sorted(set(str(url) for url in urls))
        ids = []
        for url in unique_urls:
            path, extension = _validate_rule_url(repository, url)
            source_id = source_id_for(repository, url)
            ids.append(source_id)
            old_source = source_files.get(source_id, {})
            source_new_run = old_source.get("last_seen_run_id") != run_id
            methods = []
            if url in candidate.get("readme_rule_list_urls", []):
                methods.append("readme_link")
            if url in candidate.get("seeded_source_urls", []):
                methods.append("curated_seed")
            if not methods:
                methods.append("repository_tree")
            source_files[source_id] = {
                **old_source,
                "source_id": source_id,
                "source_type": "policy_rule_list_candidate",
                "repository": repository,
                "publisher": repository,
                "url": url,
                "path": path,
                "format_hint": extension,
                "default_branch": str(candidate.get("default_branch") or "main"),
                "discovery_methods": sorted(set(methods)),
                "policy_classification": None,
                "activation_status": "NOT_ACTIVATED",
                "assessment_status": old_source.get("assessment_status", "PENDING"),
                "first_seen_at": old_source.get("first_seen_at", discovered_at),
                "last_seen_at": now if source_new_run else old_source.get("last_seen_at", now),
                "first_seen_run_id": old_source.get("first_seen_run_id", run_id),
                "last_seen_run_id": run_id if source_new_run else old_source.get("last_seen_run_id", run_id),
                "present_in_latest_discovery_inventory": True,
            }

        old_ids = old_repo.get("source_ids", [])
        if not isinstance(old_ids, list):
            old_ids = []
        merged_ids = sorted(set(old_ids) | set(ids))
        repo_record = {
            **old_repo,
            "repository": repository,
            "html_url": str(candidate.get("html_url") or ("https://github.com/" + repository)),
            "description": str(candidate.get("description") or "")[:1000],
            "default_branch": str(candidate.get("default_branch") or "main"),
            "updated_at": candidate.get("updated_at"),
            "pushed_at": candidate.get("pushed_at"),
            "stars": max(0, int(candidate.get("stars") or 0)),
            "archived": bool(candidate.get("archived", False)),
            "fork": bool(candidate.get("fork", False)),
            "license": candidate.get("license"),
            "readme_sha256": candidate.get("readme_sha256"),
            "tree_scan_status": str(candidate.get("tree_scan_status") or "not_scanned"),
            "tree_scanned_at": candidate.get("tree_scanned_at"),
            "search_queries": sorted(set(old_repo.get("search_queries", [])) | set(candidate.get("search_queries", []))),
            "source_ids": merged_ids,
            "rule_list_url_count": len(merged_ids),
            "discovery_status": (
                "RULE_FILES_DISCOVERED" if ids else
                "AWAITING_TREE_SCAN" if candidate.get("tree_scan_status") in {None, "error", "truncated"} else
                "NO_SUPPORTED_RULE_FILES_FOUND"
            ),
            "first_seen_at": old_repo.get("first_seen_at", discovered_at),
            "last_seen_at": now if is_new_run else old_repo.get("last_seen_at", now),
            "first_seen_run_id": old_repo.get("first_seen_run_id", run_id),
            "last_seen_run_id": run_id if is_new_run else old_repo.get("last_seen_run_id", run_id),
            "present_in_latest_discovery_inventory": True,
        }
        repositories[repo_key] = repo_record

    previous_latest = existing.get("latest_discovery", {})
    same_run = previous_latest.get("workflow_run_id") == run_id
    latest = previous_latest if same_run else {
        **provenance,
        "recorded_at": now,
        "mode": provenance.get("mode", "independent"),
    }
    ordered_repositories = sorted(repositories.values(), key=lambda x: x["repository"].casefold())
    ordered_sources = sorted(source_files.values(), key=lambda x: (x["repository"].casefold(), x["url"]))
    fingerprint_payload = [item["source_id"] for item in ordered_sources]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": REGISTRY_SCHEMA,
        "registry_type": "discovered_source_candidates_non_activating",
        "updated_at": existing.get("updated_at", now) if same_run else now,
        "latest_discovery": latest,
        "repository_count": len(ordered_repositories),
        "source_file_count": len(ordered_sources),
        "pending_assessment_count": sum(1 for item in ordered_sources if item.get("assessment_status") == "PENDING"),
        "discovery_fingerprint": fingerprint,
        "repositories": ordered_repositories,
        "source_files": ordered_sources,
        "policy_boundary": (
            "This is a discovery registration ledger only. It does not assign DIRECT/PROXY/REJECT, "
            "does not activate sources, and does not replace source assessment or rule-level review. "
            "External-intelligence observations are excluded from policy rule-source records."
        ),
    }



def decode_registry_storage(payload: dict) -> dict:
    """Read schema-v1 inline JSON or schema-v2 typed JSONL-shard storage."""
    if payload.get("schema_version") != 2 or payload.get("storage_format") != "typed-jsonl-shards-v1":
        return payload
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("sharded source registry records must be an array")
    repositories, source_files = [], []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("sharded source registry record must be an object")
        item = dict(record)
        kind = item.pop("record_type", "")
        if kind == "repository":
            repositories.append(item)
        elif kind == "source_file":
            source_files.append(item)
        else:
            raise ValueError("sharded source registry contains an unknown record type")
    result = {key: value for key, value in payload.items() if key != "records"}
    result.pop("storage_format", None)
    result.pop("record_count", None)
    result["schema_version"] = REGISTRY_SCHEMA
    result["repositories"] = repositories
    result["source_files"] = source_files
    return result


def encode_registry_storage(registry: dict) -> dict:
    """Convert the stable v1 logical shape to one typed, checksummed shard collection."""
    records = []
    for item in registry.get("repositories", []):
        records.append({"record_type": "repository", **item})
    for item in registry.get("source_files", []):
        records.append({"record_type": "source_file", **item})
    metadata = {key: value for key, value in registry.items()
                if key not in {"repositories", "source_files", "schema_version"}}
    return {
        **metadata,
        "schema_version": 2,
        "storage_format": "typed-jsonl-shards-v1",
        "record_count": len(records),
        "records": records,
    }

def load_discovery() -> tuple[dict, dict]:
    supplied_root = os.environ.get("AUTOMATION_SOURCE_DISCOVERY_ROOT", "").strip()
    if supplied_root:
        root = Path(supplied_root).resolve()
        runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
        if not root.is_relative_to(runner_temp) or root == runner_temp:
            raise ValueError("verified Discovery artifact root must remain beneath RUNNER_TEMP")
        path = root / "sources/discovered_sources.json"
        if not path.exists() and not path.with_name(path.name + ".manifest.json").exists():
            raise FileNotFoundError("verified Discovery artifact is missing discovered_sources.json")
        discovery = read_document(path, "candidates", {"candidates": []})
        producer = discovery.get("producer")
        if not isinstance(producer, dict):
            raise ValueError("independent Discovery artifact is missing producer provenance")
        run_id = str(producer.get("workflow_run_id", ""))
        head_sha = str(producer.get("workflow_head_sha", ""))
        if (producer.get("workflow_name") != "Shadowrocket Source Discovery (Watchdog)"
                or run_id != os.environ.get("AUTOMATION_SOURCE_DISCOVERY_RUN_ID", "")
                or not re.fullmatch(r"[0-9a-f]{40}", head_sha)):
            raise ValueError("Discovery artifact provenance does not match the verified predecessor")
        artifact_sha = os.environ.get("AUTOMATION_SOURCE_DISCOVERY_SHA256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_sha):
            raise ValueError("verified Discovery artifact digest is missing")
        return discovery, {
            "workflow_name": producer["workflow_name"],
            "workflow_run_id": run_id,
            "workflow_head_sha": head_sha,
            "artifact_sha256": artifact_sha,
            "mode": "independent",
        }

    path = ROOT / "sources/discovered_sources.json"
    discovery = read_document(path, "candidates", {"candidates": []})
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    head_sha = os.environ.get("GITHUB_SHA", "")
    if not run_id.isdigit() or not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("monolithic discovery fallback requires the current workflow run identity")
    canonical = json.dumps(discovery, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return discovery, {
        "workflow_name": os.environ.get("GITHUB_WORKFLOW", "monolithic-fallback"),
        "workflow_run_id": run_id,
        "workflow_head_sha": head_sha,
        "artifact_sha256": hashlib.sha256(canonical).hexdigest(),
        "mode": "monolithic_fallback",
    }


def main() -> int:
    try:
        discovery, provenance = load_discovery()
        if manifest_path(OUTPUT).exists():
            stored = read_document(OUTPUT, "records", {"records": []})
        elif OUTPUT.exists():
            stored = json.loads(OUTPUT.read_text(encoding="utf-8"))
        else:
            stored = {}
        existing = decode_registry_storage(stored)
        now = datetime.now(timezone.utc).isoformat()
        logical_registry = build_registry(existing, discovery, provenance, now)
        payload = encode_registry_storage(logical_registry)
        assert_resource_lease_from_environment("rulesets/source_candidate_registry.json")
        storage = write_document(
            OUTPUT, payload, "records", lease_required=True,
            force_sharded=True, max_file_bytes=MAX_REGISTRY_BYTES,
            shard_target_bytes=35_000_000,
        )
        print(json.dumps({
            "registered_repositories": logical_registry["repository_count"],
            "registered_rule_list_files": logical_registry["source_file_count"],
            "pending_assessment": logical_registry["pending_assessment_count"],
            "discovery_run_id": provenance["workflow_run_id"],
            "activated": 0,
            "output": "rulesets/source_candidate_registry.json",
            "storage": storage["storage"],
            "shard_count": storage["shards"],
            "stored_bytes": storage["bytes"],
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        import sys
        print("SOURCE CANDIDATE REGISTRY BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
