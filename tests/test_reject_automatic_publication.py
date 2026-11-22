import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_rulesets


class RejectManualApprovalTests(unittest.TestCase):
    def test_new_rule_requires_manual_approval_after_secondary_gate(self):
        line = "DOMAIN,new-ad.example"
        self.assertFalse(build_rulesets.reject_rule_authorized(line, set(), {line}, set()))
        self.assertTrue(build_rulesets.reject_rule_authorized(line, set(), {line}, {line}))
        self.assertFalse(build_rulesets.reject_rule_authorized(line, set(), set(), {line}))

    def test_new_rule_is_held_when_secondary_gate_does_not_pass(self):
        line = "DOMAIN,new-ad.example"
        self.assertFalse(build_rulesets.reject_rule_authorized(line, set(), set(), set()))
        self.assertFalse(build_rulesets.reject_rule_authorized(line, set(), set(), {line}))

    def test_existing_published_rule_is_preserved_without_new_approval(self):
        line = "DOMAIN,existing-ad.example"
        self.assertTrue(build_rulesets.reject_rule_authorized(line, {line}, set(), set()))

    def test_pending_queue_requires_current_secondary_pass_and_manual_approval(self):
        line = "DOMAIN,queued-ad.example"
        self.assertFalse(build_rulesets.reject_queue_entry_authorized(line, set(), set(), set()))
        self.assertFalse(build_rulesets.reject_queue_entry_authorized(line, set(), {line}, set()))
        self.assertFalse(build_rulesets.reject_queue_entry_authorized(line, set(), set(), {line}))
        self.assertTrue(build_rulesets.reject_queue_entry_authorized(line, set(), {line}, {line}))

    def test_previously_published_queue_item_is_preserved(self):
        line = "DOMAIN,existing-ad.example"
        self.assertTrue(build_rulesets.reject_queue_entry_authorized(line, {line}, set(), set()))

    def test_manual_approval_records_require_audit_metadata(self):
        record = {
            "rule": "DOMAIN,approved.example",
            "approved_by": "user",
            "approved_at": "2026-11-22T00:00:00Z",
            "approval_reference": "PR #123"
        }
        self.assertEqual(
            build_rulesets.manual_approved_reject_rule_lines({"manual_approved_reject_rules": [record]}),
            {"DOMAIN,approved.example"}
        )
        invalid = dict(record)
        invalid.pop("approval_reference")
        with self.assertRaises(ValueError):
            build_rulesets.manual_approved_reject_rule_lines({"manual_approved_reject_rules": [invalid]})

    def test_manual_approval_records_reject_duplicates_and_non_domain_rules(self):
        record = {
            "rule": "DOMAIN,approved.example",
            "approved_by": "user",
            "approved_at": "2026-11-22T00:00:00Z",
            "approval_reference": "PR #123"
        }
        with self.assertRaises(ValueError):
            build_rulesets.manual_approved_reject_rule_lines({"manual_approved_reject_rules": [record, record]})
        invalid = dict(record, rule="IP-CIDR,192.0.2.0/24")
        with self.assertRaises(ValueError):
            build_rulesets.manual_approved_reject_rule_lines({"manual_approved_reject_rules": [invalid]})

    def test_reject_review_queue_has_a_hard_50mb_file_limit(self):
        payload = {"schema_version": 1, "items": [{"rule": "DOMAIN,one.example"}]}
        self.assertTrue(build_rulesets.serialize_reject_review_queue(payload).endswith(b"\n"))
        original_limit = build_rulesets.MAX_REJECT_REVIEW_QUEUE_BYTES
        try:
            build_rulesets.MAX_REJECT_REVIEW_QUEUE_BYTES = 10
            with self.assertRaises(ValueError):
                build_rulesets.serialize_reject_review_queue(payload)
        finally:
            build_rulesets.MAX_REJECT_REVIEW_QUEUE_BYTES = original_limit


    def test_production_control_requires_manual_approval_after_secondary_review(self):
        import json
        control = json.loads((ROOT / "automation/production_control.json").read_text(encoding="utf-8"))
        policy = control["policy"]
        self.assertEqual(policy["reject_publication_mode"], "manual_approval_after_deterministic_gates")
        self.assertEqual(policy["manual_review_scope"], "new_reject_rules_after_deterministic_secondary_review")
        self.assertEqual(policy["manual_approved_reject_rules"], [])


if __name__ == "__main__":
    unittest.main()
