import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_ruleset_config_conflicts import classify_rule


class ConfigScopePrecedenceTests(unittest.TestCase):
    def test_same_policy_exact_overlap_is_removed(self):
        result = classify_rule(
            "DIRECT", "DOMAIN,api.example.com",
            [(12, "DOMAIN-SUFFIX,example.com,DIRECT")], []
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["effective_policy"], "DIRECT")
        self.assertEqual(result["config_line"], 12)

    def test_suffix_candidate_intersecting_exact_config_rule_is_removed(self):
        result = classify_rule(
            "PROXY", "DOMAIN-SUFFIX,example.com",
            [(7, "DOMAIN,api.example.com,PROXY")], []
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["config_line"], 7)

    def test_first_matching_config_rule_is_recorded(self):
        result = classify_rule(
            "REJECT", "DOMAIN,api.example.com",
            [
                (3, "DOMAIN,api.example.com,DIRECT"),
                (9, "DOMAIN-SUFFIX,example.com,REJECT"),
            ], []
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["config_line"], 3)
        self.assertEqual(result["effective_policy"], "DIRECT")

    def test_disjoint_scope_is_not_removed(self):
        result = classify_rule(
            "PROXY", "DOMAIN-SUFFIX,example.net",
            [(3, "DOMAIN-SUFFIX,example.com,DIRECT")], []
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_skip_proxy_overlap_is_removed_even_for_direct(self):
        result = classify_rule(
            "DIRECT", "DOMAIN,api.example.com", [], ["*.example.com"]
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["effective_policy"], "DIRECT")

    def test_conditional_overlap_is_held_not_guessed(self):
        result = classify_rule(
            "REJECT", "DOMAIN-SUFFIX,example.com",
            [(4, "AND,((DOMAIN-SUFFIX,example.com),(PROTOCOL,UDP)),REJECT")], []
        )
        self.assertEqual(result["status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
