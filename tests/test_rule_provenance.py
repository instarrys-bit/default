import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_rule_provenance import build, rule_id

class RuleProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.registry = {"sources": [
            {"id":"a","enabled":True,"url":"https://raw.githubusercontent.com/a/list","publisher":"a/list","independence_group":"ga","classification":"DIRECT","lineage_status":"unverified"},
            {"id":"b","enabled":True,"url":"https://raw.githubusercontent.com/b/list","publisher":"b/list","independence_group":"gb","classification":"DIRECT","lineage_status":"partial"}
        ]}
        self.snapshot = {"sources":[{"id":"a","sha256":"ha"},{"id":"b","sha256":"hb"}]}
        self.review = {"reviews":[{
            "domain":"example.com","policy":"DIRECT","source_entry_type":"exact_candidate",
            "status":"APPROVED","confidence":0.8,"first_seen":"2026-01-01",
            "evidence":[
                {"source_id":"a","currently_listed":True,"sha256":"ha","url":"https://raw.githubusercontent.com/a/list","publisher":"a/list","independence_group":"ga","classification":"DIRECT","lineage_status":"unverified","entry_type":"exact_candidate"},
                {"source_id":"b","currently_listed":True,"sha256":"old","url":"https://raw.githubusercontent.com/b/list","publisher":"b/list","independence_group":"gb","classification":"DIRECT","lineage_status":"partial","entry_type":"exact_candidate"}
            ]
        }]}

    def test_only_exact_current_source_snapshot_evidence_is_kept(self):
        result = build(self.review,self.registry,self.snapshot,{"rules":[]},{},{},{},{}, "now")
        rule = result["rules"][0]
        self.assertEqual([x["source_id"] for x in rule["sources"]],["a"])
        self.assertEqual(rule["sources"][0]["evidence_grade"],"snapshot_membership")
        self.assertIsNone(rule["sources"][0]["line_number"])

    def test_lineage_is_metadata_not_a_veto(self):
        result = build(self.review,self.registry,self.snapshot,{"rules":[]},{},{},{},{}, "now")
        self.assertEqual(result["rules"][0]["state"],"approved_not_published")

    def test_rule_identity_is_stable(self):
        self.assertEqual(rule_id("DIRECT","exact_candidate","example.com"),rule_id("DIRECT","exact_candidate","example.com"))

    def test_history_appends_only_when_signature_changes(self):
        first = build(self.review,self.registry,self.snapshot,{"rules":[]},{},{},{},{}, "t1")
        previous = {"rules":first["rules"]}
        second = build(self.review,self.registry,self.snapshot,previous,{},{},{},{}, "t2")
        self.assertEqual(len(second["rules"][0]["history"]),1)
        self.assertEqual(second["rules"][0]["first_seen"],"2026-01-01")

if __name__ == "__main__":
    unittest.main()
