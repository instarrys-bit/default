import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from register_discovered_sources import (build_registry, source_id_for, encode_registry_storage, decode_registry_storage)
from json_document_store import manifest_path, read_document, write_document


class DiscoveredSourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.repo = "Example/Rules"
        self.url_a = "https://raw.githubusercontent.com/Example/Rules/main/direct.list"
        self.url_b = "https://raw.githubusercontent.com/Example/Rules/main/proxy.list"
        self.discovery = {
            "schema_version": 1,
            "candidates": [{
                "repository": self.repo,
                "html_url": "https://github.com/Example/Rules",
                "default_branch": "main",
                "description": "Example domain rules",
                "stars": 12,
                "archived": False,
                "fork": False,
                "license": "MIT",
                "tree_scan_status": "complete",
                "rule_list_urls": [self.url_a, self.url_b],
                "readme_rule_list_urls": [self.url_a],
                "seeded_source_urls": [self.url_b],
                "search_queries": ["shadowrocket rules"],
                "discovered_at": "2026-11-10T00:00:00+00:00",
            }],
            "external_intelligence": {
                "observations": [{"data_type": "certificate_name", "value": "not-a-rule-source.example"}]
            },
        }
        self.provenance = {
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": "123456",
            "workflow_head_sha": "a" * 40,
            "artifact_sha256": "b" * 64,
            "mode": "independent",
        }

    def test_registers_every_repository_and_each_rule_file_separately(self):
        result = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        self.assertEqual(result["repository_count"], 1)
        self.assertEqual(result["source_file_count"], 2)
        self.assertEqual({item["url"] for item in result["source_files"]}, {self.url_a, self.url_b})
        self.assertEqual(len(result["repositories"][0]["source_ids"]), 2)

    def test_same_discovery_run_is_idempotent(self):
        first = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        second = build_registry(first, self.discovery, self.provenance, "2026-11-10T02:00:00+00:00")
        self.assertEqual(first, second)

    def test_new_discovery_run_preserves_first_seen_and_updates_last_seen(self):
        first = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        next_provenance = {**self.provenance, "workflow_run_id": "123457", "workflow_head_sha": "c" * 40, "artifact_sha256": "d" * 64}
        second = build_registry(first, self.discovery, next_provenance, "2026-11-11T01:00:00+00:00")
        self.assertEqual(second["source_files"][0]["first_seen_at"], first["source_files"][0]["first_seen_at"])
        self.assertEqual(second["source_files"][0]["last_seen_at"], "2026-11-11T01:00:00+00:00")
        self.assertEqual(second["latest_discovery"]["workflow_run_id"], "123457")

    def test_candidates_remain_unclassified_and_inactive(self):
        result = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        for item in result["source_files"]:
            self.assertIsNone(item["policy_classification"])
            self.assertEqual(item["activation_status"], "NOT_ACTIVATED")

    def test_external_intelligence_observations_are_not_rule_sources(self):
        result = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        self.assertNotIn("not-a-rule-source.example", json.dumps(result))

    def test_v1_registry_round_trips_through_typed_shard_schema(self):
        original = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        stored = encode_registry_storage(original)
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual(stored["storage_format"], "typed-jsonl-shards-v1")
        self.assertNotIn("repositories", stored)
        self.assertNotIn("source_files", stored)
        self.assertEqual(decode_registry_storage(stored), original)

    def test_v1_legacy_registry_is_accepted_without_migration_loss(self):
        original = build_registry({}, self.discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        restored = decode_registry_storage(original)
        self.assertEqual(restored, original)
        next_provenance = {**self.provenance, "workflow_run_id": "123457",
                           "workflow_head_sha": "c" * 40, "artifact_sha256": "d" * 64}
        updated = build_registry(restored, self.discovery, next_provenance,
                                 "2026-11-11T01:00:00+00:00")
        self.assertEqual(updated["repository_count"], 1)
        self.assertEqual(updated["source_file_count"], 2)
        self.assertEqual(updated["source_files"][0]["first_seen_run_id"], "123456")

    def test_1647_repositories_and_47457_rule_files_survive_shard_round_trip(self):
        candidates = []
        total_urls = 47457
        for index in range(1647):
            count = 29 if index < 1341 else 28
            repository = f"scale-org-{index // 100}/rules-{index}"
            urls = [
                f"https://raw.githubusercontent.com/{repository}/main/rules/part-{part:03d}.list"
                for part in range(count)
            ]
            candidates.append({
                "repository": repository,
                "default_branch": "main",
                "rule_list_urls": urls,
                "tree_scan_status": "complete",
                "discovered_at": "2026-11-10T00:00:00+00:00",
            })
        self.assertEqual(sum(len(item["rule_list_urls"]) for item in candidates), total_urls)
        discovery = {"schema_version": 1, "candidates": candidates}
        logical = build_registry({}, discovery, self.provenance, "2026-11-10T01:00:00+00:00")
        self.assertEqual(logical["repository_count"], 1647)
        self.assertEqual(logical["source_file_count"], total_urls)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_candidate_registry.json"
            stored = encode_registry_storage(logical)
            result = write_document(
                path, stored, "records", lease_required=False,
                force_sharded=True, max_file_bytes=40_000_000,
                shard_target_bytes=35_000_000,
            )
            self.assertEqual(result["storage"], "jsonl-shards-v1")
            manifest = json.loads(manifest_path(path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["record_count"], 1647 + total_urls)
            self.assertTrue(all(item["bytes"] <= 40_000_000 for item in manifest["shards"]))
            restored = decode_registry_storage(read_document(path, "records"))
            self.assertEqual(restored["repository_count"], 1647)
            self.assertEqual(restored["source_file_count"], total_urls)
            self.assertEqual(restored["discovery_fingerprint"], logical["discovery_fingerprint"])
            self.assertEqual(restored["source_files"][0]["source_id"],
                             logical["source_files"][0]["source_id"])

    def test_rejects_rule_url_from_another_repository(self):
        invalid = json.loads(json.dumps(self.discovery))
        invalid["candidates"][0]["rule_list_urls"] = [
            "https://raw.githubusercontent.com/Other/Repo/main/foreign.list"
        ]
        with self.assertRaises(ValueError):
            build_registry({}, invalid, self.provenance, "2026-11-10T01:00:00+00:00")

    def test_stable_source_id_is_repository_and_file_specific(self):
        self.assertNotEqual(source_id_for(self.repo, self.url_a), source_id_for(self.repo, self.url_b))
        self.assertEqual(source_id_for(self.repo, self.url_a), source_id_for(self.repo, self.url_a))


if __name__ == "__main__":
    unittest.main()
