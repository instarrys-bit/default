import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_source_lineage import audit_registry


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


if __name__ == "__main__":
    unittest.main()
