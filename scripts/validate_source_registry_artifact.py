#!/usr/bin/env python3
"""Read-only replay of a pinned Source Discovery artifact through registry/shard code."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from json_document_store import manifest_path, read_document, write_document
from register_discovered_sources import build_registry, decode_registry_storage, encode_registry_storage

ROOT = Path(__file__).resolve().parents[1]


def load_existing_registry(path: Path) -> dict:
    """Read the complete historical inline or sharded registry without mutating it."""
    if not path.is_file() and not manifest_path(path).is_file():
        return {}
    stored = read_document(path, "records", {"records": []})
    return decode_registry_storage(stored)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-root", required=True, type=Path)
    parser.add_argument("--artifact-zip", required=True, type=Path)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--expected-inventory-sha256", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--existing-registry", type=Path, default=ROOT / "rulesets/source_candidate_registry.json")
    args = parser.parse_args()

    artifact_bytes = args.artifact_zip.read_bytes()
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    if artifact_sha != args.expected_artifact_sha256:
        raise SystemExit(f"artifact ZIP SHA-256 mismatch: {artifact_sha}")

    inventory_path = args.discovery_root / "sources/discovered_sources.json"
    inventory_bytes = inventory_path.read_bytes()
    inventory_sha = hashlib.sha256(inventory_bytes).hexdigest()
    if inventory_sha != args.expected_inventory_sha256:
        raise SystemExit(f"discovery inventory SHA-256 mismatch: {inventory_sha}")

    discovery = json.loads(inventory_bytes)
    producer = discovery.get("producer")
    if not isinstance(producer, dict):
        raise SystemExit("Discovery producer provenance is missing")
    if producer.get("workflow_name") != "Shadowrocket Source Discovery (Watchdog)":
        raise SystemExit("unexpected Discovery workflow name")
    if str(producer.get("workflow_run_id")) != args.expected_run_id:
        raise SystemExit("Discovery run ID does not match pinned predecessor")
    if producer.get("workflow_head_sha") != args.expected_head_sha:
        raise SystemExit("Discovery head SHA does not match pinned predecessor")

    provenance = {
        "workflow_name": producer["workflow_name"],
        "workflow_run_id": str(producer["workflow_run_id"]),
        "workflow_head_sha": producer["workflow_head_sha"],
        "artifact_sha256": artifact_sha,
        "mode": "independent",
    }
    existing = load_existing_registry(args.existing_registry)
    logical = build_registry(existing, discovery, provenance, "2026-11-10T05:00:00+00:00")
    new_repositories = len({str(item.get("repository", "")).lower() for item in discovery["candidates"]})
    new_sources = len({str(url).strip() for candidate in discovery["candidates"] for url in candidate.get("rule_list_urls", []) if str(url).strip()})
    if logical["repository_count"] < new_repositories:
        raise SystemExit("historical merge lost one or more discovered repositories")
    if logical["source_file_count"] < new_sources:
        raise SystemExit("historical merge lost one or more discovered source files")
    expected_repositories = logical["repository_count"]
    expected_sources = logical["source_file_count"]

    typed = encode_registry_storage(logical)
    with tempfile.TemporaryDirectory(prefix="source-registry-artifact-dryrun-") as temp:
        path = Path(temp) / "source_candidate_registry.json"
        written = write_document(
            path,
            typed,
            "records",
            lease_required=True,
            force_sharded=True,
            max_file_bytes=40_000_000,
            shard_target_bytes=35_000_000,
        )
        manifest_file = manifest_path(path)
        if not manifest_file.is_file() or path.exists():
            raise SystemExit("sharded registry manifest did not become the sole commit point")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("record_count") != expected_repositories + expected_sources:
            raise SystemExit("manifest record count mismatch")
        if manifest.get("max_file_bytes") != 40_000_000:
            raise SystemExit("manifest did not preserve the 40 MB per-file cap")
        if any(int(shard.get("bytes", -1)) > 40_000_000 for shard in manifest.get("shards", [])):
            raise SystemExit("a shard exceeds the 40 MB per-file cap")

        reconstructed = decode_registry_storage(read_document(path, "records"))
        if reconstructed != logical:
            raise SystemExit("sharded read-back differs from the logical registry")
        if reconstructed["discovery_fingerprint"] != logical["discovery_fingerprint"]:
            raise SystemExit("discovery fingerprint changed during shard round-trip")

        print(json.dumps({
            "status": "PASS",
            "mode": "read_only_tempdir",
            "discovery_run_id": provenance["workflow_run_id"],
            "discovery_head_sha": provenance["workflow_head_sha"],
            "artifact_sha256": artifact_sha,
            "inventory_sha256": inventory_sha,
            "historical_repository_count": len(existing.get("repositories", [])),
            "historical_source_file_count": len(existing.get("source_files", [])),
            "new_repository_count": new_repositories,
            "new_source_file_count": new_sources,
            "repository_count": logical["repository_count"],
            "source_file_count": logical["source_file_count"],
            "typed_record_count": manifest["record_count"],
            "shard_count": written["shards"],
            "shard_bytes": written["bytes"],
            "manifest_sha256": hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
            "discovery_fingerprint": logical["discovery_fingerprint"],
            "activation_count": 0,
            "production_files_modified": False,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
