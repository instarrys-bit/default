import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_source_lineage import audit_registry, shared_reference_pairs


class SourceLineageIsolationTests(unittest.TestCase):
    def test_missing_or_unavailable_lineage_documents_do_not_abort_registry_audit(self):
        config = {"sources": [
            {"id": "missing-url", "publisher": "one/source", "lineage_status": "unverified"},
            {"id": "offline-url", "publisher": "two/source", "lineage_status": "unverified", "lineage_evidence_url": "https://github.com/two/source/blob/main/README.md"}
        ]}
        def fail_fetch(url):
            raise OSError("temporary lineage host outage")
        report = audit_registry(config, fetcher=fail_fetch)
        self.assertEqual(report["source_count"], 2)
        self.assertEqual(report["audited_source_count"], 0)
        self.assertEqual(report["sources"][0]["status"], "missing_evidence_url")
        self.assertEqual(report["sources"][1]["status"], "evidence_unavailable")
        self.assertEqual(report["lineage_unverified_count"], 2)

    def test_successful_lineage_inventory_never_upgrades_lineage_status(self):
        config = {"sources": [{
            "id": "source-one",
            "publisher": "one/source",
            "lineage_status": "unverified",
            "lineage_evidence_url": "https://github.com/one/source/blob/main/README.md",
            "upstream_repositories": []
        }]}
        report = audit_registry(config, fetcher=lambda url: b"Upstream: https://github.com/example/upstream")
        self.assertEqual(report["audited_source_count"], 1)
        self.assertEqual(report["sources"][0]["status"], "audited")
        self.assertEqual(report["sources"][0]["lineage_status"], "unverified")
        self.assertEqual(report["lineage_verified_count"], 0)

    def test_shared_reference_index_preserves_pairwise_overlap_without_comparing_unrelated_rows(self):
        records = [
            {"repository": "one/a", "status": "ok", "refs": ["x", "y", "x"]},
            {"repository": "two/b", "status": "ok", "refs": ["y", "z"]},
            {"repository": "three/c", "status": "ok", "refs": ["z"]},
            {"repository": "four/d", "status": "error", "refs": ["x", "z"]},
        ]
        pairs = shared_reference_pairs(records, "refs", "ok")
        self.assertEqual(pairs, [
            {"left": 0, "right": 1, "shared": ["y"]},
            {"left": 1, "right": 2, "shared": ["z"]},
        ])

    def test_candidate_readme_is_reused_when_discovery_hash_matches(self):
        config = {"sources": []}
        candidates = [{
            "repository": "example/rules",
            "default_branch": "main",
            "readme_sha256": "a" * 64,
            "rule_list_urls": ["https://raw.githubusercontent.com/example/rules/main/list.list"],
        }]
        prior = {"candidate_sources": [{
            "repository": "example/rules",
            "readme_url": "https://raw.githubusercontent.com/example/rules/main/README.md",
            "readme_sha256": "a" * 64,
            "referenced_repositories": ["upstream/base"],
            "reference_count": 1,
            "lineage_status": "unverified",
            "status": "audited_reference_inventory",
        }]}
        def unexpected_fetch(url):
            raise AssertionError("unchanged README should be served from the validated prior snapshot")
        report = audit_registry(config, fetcher=unexpected_fetch, candidates=candidates, previous_report=prior)
        self.assertEqual(report["candidate_readme_audited_count"], 1)
        self.assertEqual(report["candidate_sources"][0]["referenced_repositories"], ["upstream/base"])


if __name__ == "__main__":
    unittest.main()
