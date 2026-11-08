import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from domain_rule_engine import DomainRule, RuleIndex, inspect_suffix_scope


class SuffixScopeSafetyTests(unittest.TestCase):
    def test_parent_suffix_is_not_blocked_by_descendant_exact_exception(self):
        rules = RuleIndex([DomainRule("DOMAIN", "api.example.com", "PROXY", 10, "DOMAIN,api.example.com,PROXY")])
        status, _ = inspect_suffix_scope("example.com", "DIRECT", rules, [], {})
        self.assertIsNone(status)

    def test_suffix_index_preserves_covering_rules_among_many_unrelated_rules(self):
        unrelated = [
            DomainRule("DOMAIN-SUFFIX", f"unrelated-{i}.invalid", "DIRECT", i + 1,
                       f"DOMAIN-SUFFIX,unrelated-{i}.invalid,DIRECT")
            for i in range(1500)
        ]
        covering = DomainRule(
            "DOMAIN-SUFFIX", "example.com", "PROXY", 2000,
            "DOMAIN-SUFFIX,example.com,PROXY"
        )
        rules = RuleIndex(unrelated + [covering])
        status, reason = inspect_suffix_scope("sub.example.com", "DIRECT", rules, [], {})
        self.assertEqual(status, "CONFLICT")
        self.assertIn("fully covering config suffix scope", reason)

    def test_suffix_is_held_for_conflicting_ancestor_suffix_rule(self):
        rules = RuleIndex([DomainRule("DOMAIN-SUFFIX", "example.com", "PROXY", 10, "DOMAIN-SUFFIX,example.com,PROXY")])
        status, _ = inspect_suffix_scope("sub.example.com", "DIRECT", rules, [], {})
        self.assertEqual(status, "CONFLICT")

    def test_suffix_is_held_when_it_would_cover_a_protected_exact_host(self):
        rules = RuleIndex([])
        status, _ = inspect_suffix_scope("example.com", "REJECT", rules, [], {"protected_exact": ["login.example.com"]})
        self.assertEqual(status, "RISK_HOLD")

    def test_suffix_is_held_when_it_intersects_a_conditional_domain_rule(self):
        rules = RuleIndex([])
        status, _ = inspect_suffix_scope("example.com", "DIRECT", rules, [(12, "AND,((DOMAIN,api.example.com),(GEOIP,CN)),DIRECT")], {})
        self.assertEqual(status, "REVIEW")


    def test_proxy_suffix_ignores_narrower_skip_proxy_exception(self):
        rules = RuleIndex([])
        status, _ = inspect_suffix_scope("example.com", "PROXY", rules, [], {}, ["*.sub.example.com"])
        self.assertIsNone(status)

    def test_proxy_suffix_is_held_when_wildcard_parent_covers_full_scope(self):
        rules = RuleIndex([])
        status, _ = inspect_suffix_scope("example.com", "PROXY", rules, [], {}, ["*.example.com"])
        self.assertEqual(status, "CONFLICT")

if __name__ == "__main__":
    unittest.main()
