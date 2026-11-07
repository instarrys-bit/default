import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_rulesets import build_publication_accounting


class PublicationAccountingTests(unittest.TestCase):
    def test_promoted_queue_rule_explains_one_rule_publication_delta(self):
        approved = {("DIRECT", "exact_candidate", "approved.example")}
        published = approved | {("PROXY", "suffix_candidate", "promoted.example")}
        promoted = {("PROXY", "suffix_candidate", "promoted.example")}
        result = build_publication_accounting(published, approved, promoted, 1)
        self.assertEqual(result["published_rule_total"], 2)
        self.assertEqual(result["approved_review_total"], 1)
        self.assertEqual(result["promoted_queue_total"], 1)
        self.assertEqual(result["promoted_queue_published_without_current_approval_total"], 1)
        self.assertEqual(result["retained_published_without_current_approval_total"], 0)
        self.assertEqual(result["published_count_delta_vs_approved_review_total"], 1)
        self.assertTrue(result["accounting_reconciled"])

    def test_retained_rule_without_current_approval_is_explicit(self):
        approved = {("DIRECT", "exact_candidate", "approved.example")}
        published = approved | {("DIRECT", "exact_candidate", "legacy.example")}
        result = build_publication_accounting(published, approved, set(), 1)
        self.assertEqual(result["retained_published_without_current_approval_total"], 1)
        self.assertEqual(
            result["published_without_current_approval_sample"],
            ["DIRECT|DOMAIN|legacy.example"],
        )

    def test_approved_but_unpublished_rules_are_reported(self):
        approved = {
            ("DIRECT", "exact_candidate", "published.example"),
            ("PROXY", "exact_candidate", "queued.example"),
        }
        published = {("DIRECT", "exact_candidate", "published.example")}
        result = build_publication_accounting(published, approved, set(), 2)
        self.assertEqual(result["approved_review_not_published_total"], 1)
        self.assertEqual(result["published_count_delta_vs_approved_review_total"], -1)
        self.assertTrue(result["accounting_reconciled"])

    def test_approved_counter_must_match_unique_rule_identities(self):
        with self.assertRaisesRegex(ValueError, "approved review counter"):
            build_publication_accounting(
                {("DIRECT", "exact_candidate", "a.example")},
                set(),
                set(),
                1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
