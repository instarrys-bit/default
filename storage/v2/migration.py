"""V1-to-V2 reference-only migration manifest validation."""
from __future__ import annotations

import re
from collections import Counter


MIGRATABLE_PREFIXES = ("data/", "sources/", "rulesets/", "reports/")
MIGRATABLE_AUTOMATION_FILES = {
    "automation/task_queue.json",
    "automation/production_control.json",
    "automation/production_inputs.json",
    "automation/release_manifest.json",
}
BLOB_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def is_migratable_path(path: str) -> bool:
    return path.startswith(MIGRATABLE_PREFIXES) or path in MIGRATABLE_AUTOMATION_FILES


def validate_migration_manifest(manifest: object, inventory: object) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported migration manifest schema")
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise ValueError("unsupported V1 inventory schema")
    archive = manifest.get("source_archive")
    if not isinstance(archive, dict):
        raise ValueError("source_archive is required")
    for field in ("branch", "commit", "tree_sha", "inventory_path", "inventory_blob_sha"):
        if not isinstance(archive.get(field), str) or not archive[field]:
            raise ValueError(f"source_archive.{field} is required")
    if archive["branch"] != inventory.get("archive_branch") or archive["commit"] != inventory.get("archive_commit"):
        raise ValueError("migration source does not match the frozen V1 archive")
    if archive["tree_sha"] != inventory.get("tree_sha"):
        raise ValueError("migration tree SHA does not match V1 inventory")
    if archive.get("tracked_file_count") != inventory.get("file_count"):
        raise ValueError("migration tracked-file count does not match V1 inventory")

    inventory_files = inventory.get("files")
    entries = manifest.get("entries")
    if not isinstance(inventory_files, list) or not isinstance(entries, list):
        raise ValueError("inventory files and migration entries must be arrays")
    expected = {x.get("path"): x for x in inventory_files if isinstance(x, dict) and is_migratable_path(x.get("path", ""))}
    seen = set()
    counts = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("migration entry must be an object")
        path = entry.get("source_path")
        if not isinstance(path, str) or path in seen:
            raise ValueError("migration source paths must be unique non-empty strings")
        seen.add(path)
        source = expected.get(path)
        if source is None:
            raise ValueError(f"migration path is not in the V1 allowlisted inventory: {path}")
        if entry.get("source_blob_sha") != source.get("blob_sha") or entry.get("source_size_bytes") != source.get("size_bytes"):
            raise ValueError(f"source blob identity mismatch: {path}")
        if not BLOB_SHA_RE.fullmatch(str(entry.get("source_blob_sha", ""))):
            raise ValueError(f"invalid Git blob SHA: {path}")
        if entry.get("migration_status") != "DISCOVERED_NOT_IMPORTED":
            raise ValueError("initial migration manifest must not claim data was imported")
        if entry.get("promotion_status") != "QUARANTINED_PENDING_VALIDATION":
            raise ValueError("all V1 records must remain quarantined pending validation")
        if path == "automation/task_queue.json" and entry.get("asset_class") != "LEGACY_QUEUE_SNAPSHOT_HISTORICAL_ONLY":
            raise ValueError("legacy queue snapshot must remain historical-only")
        counts[entry.get("asset_class")] += 1

    if seen != set(expected):
        missing = sorted(set(expected) - seen)
        extra = sorted(seen - set(expected))
        raise ValueError(f"migration inventory coverage mismatch; missing={missing}, extra={extra}")
    summary = manifest.get("summary")
    if not isinstance(summary, dict) or summary.get("entry_count") != len(entries):
        raise ValueError("migration summary entry_count mismatch")
    if summary.get("by_asset_class") != dict(counts):
        raise ValueError("migration summary asset-class counts mismatch")
    if summary.get("all_status") != "DISCOVERED_NOT_IMPORTED":
        raise ValueError("migration summary must remain not imported")

    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("migration policy is required")
    for field in ("archive_is_immutable", "sha_verification_required_before_read",
                  "schema_and_lineage_validation_required_before_acceptance",
                  "duplicate_and_conflict_analysis_required", "no_automatic_publication"):
        if policy.get(field) is not True:
            raise ValueError(f"migration policy {field} must be true")
    for field in ("legacy_task_statuses_imported", "legacy_active_leases_imported", "legacy_tasks_auto_replayed"):
        if policy.get(field) is not False:
            raise ValueError(f"migration policy {field} must be false")

    config = manifest.get("user_configuration_reference")
    archived_config = next((x for x in inventory_files if isinstance(x, dict) and x.get("path") == "modules/uu.conf"), None)
    if not isinstance(config, dict) or config.get("path") != "modules/uu.conf":
        raise ValueError("user configuration reference is required")
    if not archived_config or config.get("source_archive_blob_sha") != archived_config.get("blob_sha"):
        raise ValueError("archived uu.conf reference must match the frozen inventory")
    if not BLOB_SHA_RE.fullmatch(str(config.get("current_main_blob_sha", ""))):
        raise ValueError("current main uu.conf SHA must be recorded")
    if config.get("automation_access") != "READ_ONLY" or config.get("manual_user_access") != "ALLOWED":
        raise ValueError("uu.conf protection must apply only to automation, not manual user edits")
    if config.get("migration") != "REFERENCE_ONLY; NEVER WRITE OR REPLACE":
        raise ValueError("uu.conf must remain a reference-only user-owned file")

    return {
        "valid": True,
        "entry_count": len(entries),
        "asset_class_counts": dict(counts),
        "archive_commit": archive["commit"],
        "user_config_manual_edits_allowed": True,
        "legacy_queue_imported": False,
    }
