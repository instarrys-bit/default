import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_rulesets import promote_queue_to_capacity, previously_published_reject_rules, POLICIES


class RuleSetCapacityTests(unittest.TestCase):
    def make_queue(self):
        return {
            ("DIRECT", "exact_candidate", "d1.example"): {"priority": 1, "queued_at": "2026-01-01T00:00:00Z"},
            ("PROXY", "suffix_candidate", "p1.example"): {"priority": 2, "queued_at": "2026-01-01T00:00:00Z"},
            ("REJECT", "exact_candidate", "r1.example"): {"priority": 3, "queued_at": "2026-01-01T00:00:00Z"}
        }

    def test_29999_published_promotes_only_one_rule(self):
        rule_sets = {policy: set() for policy in POLICIES}
        queue = self.make_queue()
        promoted = promote_queue_to_capacity(rule_sets, queue, 29999)
        self.assertEqual(len(promoted), 1)
        self.assertEqual(sum(len(x) for x in rule_sets.values()), 1)
        self.assertEqual(len(queue), 2)

    def test_30000_published_keeps_all_new_rules_in_queue(self):
        rule_sets = {policy: set() for policy in POLICIES}
        queue = self.make_queue()
        promoted = promote_queue_to_capacity(rule_sets, queue, 30000)
        self.assertEqual(promoted, [])
        self.assertEqual(sum(len(x) for x in rule_sets.values()), 0)
        self.assertEqual(len(queue), 3)

    def test_over_capacity_existing_publication_fails_closed(self):
        with self.assertRaises(ValueError):
            promote_queue_to_capacity({policy: set() for policy in POLICIES}, self.make_queue(), 30001)

    def test_priority_and_fifo_order_are_preserved(self):
        rule_sets = {policy: set() for policy in POLICIES}
        queue = self.make_queue()
        promoted = promote_queue_to_capacity(rule_sets, queue, 29998)
        self.assertEqual(promoted[0][0], "DIRECT")
        self.assertEqual(promoted[1][0], "PROXY")
        self.assertEqual(len(queue), 1)

    def test_already_published_queue_duplicate_does_not_consume_capacity(self):
        rule_sets = {policy: set() for policy in POLICIES}
        rule_sets["DIRECT"].add(("exact_candidate", "d1.example"))
        queue = self.make_queue()
        promoted = promote_queue_to_capacity(rule_sets, queue, 29999)
        self.assertEqual(len(promoted), 2)
        self.assertEqual(len(rule_sets["PROXY"]), 1)
        self.assertEqual(len(queue), 1)

    def test_superseded_published_reject_keeps_prior_authorization(self):
        archive = {"items": [{
            "policy": "REJECT",
            "rule": "DOMAIN,ads.example.com",
            "origin": "published_ruleset",
            "superseded_at": "2026-11-03T00:00:00+00:00",
            "restored_at": None,
        }]}
        authorized = previously_published_reject_rules(set(), archive)
        self.assertIn("DOMAIN,ads.example.com", authorized)

    def test_pending_reject_archive_does_not_grant_prior_publication_authorization(self):
        archive = {"items": [{
            "policy": "REJECT",
            "rule": "DOMAIN,ads.example.com",
            "origin": "pending_queue",
            "superseded_at": "2026-11-03T00:00:00+00:00",
            "restored_at": None,
        }]}
        authorized = previously_published_reject_rules(set(), archive)
        self.assertNotIn("DOMAIN,ads.example.com", authorized)


if __name__ == "__main__":
    unittest.main()
