import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from register_discovered_sources import build_registry, source_id_for


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
