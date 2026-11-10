import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_rulesets import (
    load_reject_approvals, load_reject_approval_document,
    reject_rule_authorized, revalidate_manual_reject_queue_item,
)


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

    def test_approval_snapshot_must_match_the_approved_rule_set(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approvals.json"
            item = {
                "rule": "DOMAIN,approved.example",
                "domain": "approved.example",
                "scope": "exact_candidate",
                "policy": "REJECT",
                "status": "ELIGIBLE_FOR_MANUAL_APPROVAL",
            }
            path.write_text(json.dumps({
                "schema_version": 1,
                "approved_rules": ["DOMAIN,approved.example"],
                "approval_source": {
                    "path": "rulesets/reject_review_queue.json",
                    "git_blob_sha": "a" * 40,
                    "queue_updated_at": "2026-11-09T00:00:00Z",
                    "approved_item_count": 1,
                },
                "approved_queue_items": [item],
            }), encoding="utf-8")
            document = load_reject_approval_document(path)
            self.assertEqual(document["approved_rules"], {"DOMAIN,approved.example"})
            self.assertEqual(document["approved_queue_items"], [item])

    def test_approval_snapshot_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "approvals.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "approved_rules": ["DOMAIN,approved.example"],
                "approval_source": {
                    "path": "rulesets/reject_review_queue.json",
                    "git_blob_sha": "a" * 40,
                    "queue_updated_at": "2026-11-09T00:00:00Z",
                    "approved_item_count": 1,
                },
                "approved_queue_items": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_reject_approval_document(path)

    def test_manual_queue_item_requires_current_source_evidence(self):
        source_ids = ["s1", "s2", "s3"]
        source_map = {}
        hashes = {}
        evidence = []
        for index, source_id in enumerate(source_ids):
            publisher = f"publisher-{index}"
            url = f"https://example.test/{source_id}.list"
            source = {
                "id": source_id,
                "publisher": publisher,
                "independence_group": f"group-{index}",
                "lineage_status": "verified",
                "policy_evidence": "documented_policy",
                "upstream_repositories": [],
                "classification": "REJECT",
                "url": url,
                "enabled": True,
            }
            source_map[source_id] = source
            hashes[source_id] = str(index + 1) * 64
            evidence.append({
                "source_id": source_id,
                "entry_type": "exact_candidate",
                "publisher": publisher,
                "independence_group": source["independence_group"],
                "lineage_status": "verified",
                "policy_evidence": "documented_policy",
                "upstream_repositories": [],
                "classification": "REJECT",
                "url": url,
                "sha256": hashes[source_id],
                "currently_listed": True,
            })
        item = {
            "rule": "DOMAIN,approved.example",
            "domain": "approved.example",
            "scope": "exact_candidate",
            "policy": "REJECT",
            "status": "ELIGIBLE_FOR_MANUAL_APPROVAL",
            "confidence": 1.0,
            "current_source_count": 3,
            "independent_publisher_count": 2,
            "source_ids": source_ids,
            "publishers": [source_map[sid]["publisher"] for sid in source_ids],
            "independent_publisher_groups": [
                [source_map["s1"]["publisher"]],
                [source_map["s2"]["publisher"], source_map["s3"]["publisher"]],
            ],
        }
        scoring = {
            "source_weights": {sid: 0.4 for sid in source_ids},
            "required_sources_by_policy": {"REJECT": []},
            "reject_secondary_review": {
                "minimum_current_sources": 3,
                "minimum_independent_publishers": 2,
                "required_any_sources": ["s1"],
            },
        }
        candidate_map = {
            "approved.example": {
                "candidate_policies": ["REJECT"],
                "evidence": evidence,
            }
        }
        result = revalidate_manual_reject_queue_item(
            item, candidate_map, source_map, hashes, set(source_ids),
            scoring, 2, 0.8, set(),
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["secondary"]["current_source_count"], 3)

        missing_source_ids = {"s1", "s2"}
        blocked = revalidate_manual_reject_queue_item(
            item, candidate_map, source_map, hashes, missing_source_ids,
            scoring, 2, 0.8, set(),
        )
        self.assertFalse(blocked["eligible"])
        self.assertIn("approved_source_evidence_no_longer_current", blocked["reasons"])

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
