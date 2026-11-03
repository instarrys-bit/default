import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_ruleset_config_overlap import (
    all_rule_lines,
    audit,
    match_candidate,
    scope_covers_candidate,
    skip_proxy_match,
)


class RulesetConfigOverlapTests(unittest.TestCase):
    def test_scope_audit_reads_all_rule_lines_without_ordering(self):
        config = """[Rule]
RULE-SET,https://example.invalid/proxy.list,PROXY
DOMAIN,late.example.com,REJECT
[Host]
"""
        self.assertEqual(all_rule_lines(config), [
            (2, "RULE-SET,https://example.invalid/proxy.list,PROXY"),
            (3, "DOMAIN,late.example.com,REJECT"),
        ])

    def test_exact_candidate_is_covered_by_exact_or_parent_suffix(self):
        self.assertTrue(scope_covers_candidate("exact_candidate", "api.example.com", "DOMAIN", "api.example.com"))
        self.assertTrue(scope_covers_candidate("exact_candidate", "api.example.com", "DOMAIN-SUFFIX", "example.com"))

    def test_child_exact_exception_does_not_cover_parent_suffix_candidate(self):
        self.assertFalse(scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN", "api.example.com"))
        self.assertFalse(scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN-SUFFIX", "api.example.com"))

    def test_parent_suffix_covers_full_suffix_candidate(self):
        self.assertTrue(scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN-SUFFIX", "example.com"))
        self.assertTrue(scope_covers_candidate("suffix_candidate", "api.example.com", "DOMAIN-SUFFIX", "example.com"))

    def test_mixed_policy_coverage_is_reported_without_selecting_a_winner(self):
        rules = [
            (2, "DOMAIN-SUFFIX,example.com,DIRECT"),
            (3, "DOMAIN,api.example.com,PROXY"),
        ]
        result = match_candidate("api.example.com", "DIRECT", rules)
        self.assertEqual(result["status"], "MIXED_POLICY_COVERAGE")
        self.assertIsNone(result["effective_policy"])
        self.assertEqual(len(result["matches"]), 2)
        self.assertIn("not evaluated", result["reason"])

    def test_reject_config_scope_is_included_in_automated_audit(self):
        result = match_candidate("api.example.com", "DIRECT", [(2, "DOMAIN,api.example.com,REJECT")])
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["matches"][0]["policy"], "REJECT")

    def test_keyword_and_conditional_rules_are_not_evaluated(self):
        keyword = match_candidate("api.example.com", "DIRECT", [(2, "DOMAIN-KEYWORD,example,REJECT")])
        conditional = match_candidate("api.example.com", "DIRECT", [(2, "AND,((DOMAIN-SUFFIX,example.com),(GEOIP,CN)),DIRECT")])
        self.assertEqual(keyword["status"], "NOT_COVERED_BY_CONFIG_SCOPE")
        self.assertEqual(conditional["status"], "NOT_COVERED_BY_CONFIG_SCOPE")

    def test_skip_proxy_exact_entry_does_not_cover_parent_suffix(self):
        self.assertIsNone(skip_proxy_match("example.com", ["api.example.com"], "suffix_candidate"))
        self.assertEqual(skip_proxy_match("api.example.com", ["*.example.com"], "exact_candidate"), "*.example.com")

    def test_skip_proxy_wildcard_parent_covers_suffix_candidate(self):
        self.assertEqual(skip_proxy_match("example.com", ["*.example.com"], "suffix_candidate"), "*.example.com")
        self.assertIsNone(skip_proxy_match("example.com", ["*.api.example.com"], "suffix_candidate"))

    def test_audit_reports_scope_coverage_without_precedence_fields(self):
        config = "[General]\nskip-proxy = \n[Rule]\nDOMAIN,api.example.com,PROXY\nRULE-SET,https://example.invalid/direct.list,DIRECT\n[Host]\n"
        ledger = {"reviews": [{"domain": "api.example.com", "policy": "DIRECT", "status": "APPROVED"}]}
        report = audit(config, ledger)
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["results"][0]["status"], "CONFLICT")
        self.assertNotIn("priority_resolution", report["results"][0])
        self.assertIn("No rule order", " ".join(report["limitations"]))


if __name__ == "__main__":
    unittest.main()
