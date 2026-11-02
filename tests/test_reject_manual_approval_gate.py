import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_rulesets import load_reject_approvals, reject_rule_authorized


class RejectManualApprovalTests(unittest.TestCase):
    def test_unapproved_new_rule_is_held(self):
        line = "DOMAIN,new-ad.example"
        self.assertFalse(reject_rule_authorized(line, set(), set()))

    def test_existing_published_rule_is_preserved(self):
        line = "DOMAIN,existing-ad.example"
        self.assertTrue(reject_rule_authorized(line, {line}, set()))

    def test_explicit_manual_approval_allows_rule(self):
        line = "DOMAIN-SUFFIX,approved-ad.example"
        self.assertTrue(reject_rule_authorized(line, set(), {line}))

    def test_approval_ledger_normalizes_case(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approvals.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "approved_rules": ["domain,Example.COM"]
            }), encoding="utf-8")
            self.assertEqual(load_reject_approvals(path), {"DOMAIN,example.com"})

    def test_malformed_approval_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approvals.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "approved_rules": ["DOMAIN,not a domain"]
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_reject_approvals(path)


if __name__ == "__main__":
    unittest.main()
