import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_ruleset_config_conflicts import classify_rule


class ConfigScopeCoverageTests(unittest.TestCase):
    def test_same_policy_exact_scope_coverage_is_removed_without_winner(self):
        result = classify_rule(
            "DIRECT", "DOMAIN,api.example.com",
            [(12, "DOMAIN-SUFFIX,example.com,DIRECT")], []
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["effective_policy"])
        self.assertIsNone(result["config_line"])
        self.assertIn("DOMAIN-SUFFIX,example.com", result["config_rule"])

    def test_narrower_exact_exception_does_not_cover_parent_suffix(self):
        result = classify_rule(
            "PROXY", "DOMAIN-SUFFIX,example.com",
            [(7, "DOMAIN,api.example.com,REJECT")], []
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_all_covering_scopes_are_recorded_without_winner(self):
        result = classify_rule(
            "REJECT", "DOMAIN,api.example.com",
            [
                (3, "DOMAIN,api.example.com,DIRECT"),
                (9, "DOMAIN-SUFFIX,example.com,PROXY"),
            ], []
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["config_line"])
        self.assertIsNone(result["effective_policy"])
        self.assertIn("L3:", result["config_rule"])
        self.assertIn("L9:", result["config_rule"])

    def test_disjoint_scope_is_not_removed(self):
        result = classify_rule(
            "PROXY", "DOMAIN-SUFFIX,example.net",
            [(3, "DOMAIN-SUFFIX,example.com,DIRECT")], []
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_skip_proxy_full_coverage_is_removed_even_for_direct(self):
        result = classify_rule(
            "DIRECT", "DOMAIN,api.example.com", [], ["*.example.com"]
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["effective_policy"])

    def test_exact_skip_proxy_exception_does_not_cover_parent_suffix(self):
        result = classify_rule(
            "DIRECT", "DOMAIN-SUFFIX,example.com", [], ["api.example.com"]
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_conditional_overlap_is_not_evaluated_by_scope_sync(self):
        result = classify_rule(
            "REJECT", "DOMAIN-SUFFIX,example.com",
            [(4, "AND,((DOMAIN-SUFFIX,example.com),(PROTOCOL,UDP)),REJECT")], []
        )
        self.assertEqual(result["status"], "NO_CONFLICT")


if __name__ == "__main__":
    unittest.main()
