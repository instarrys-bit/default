import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from domain_rule_engine import DomainRule, RuleIndex, inspect_suffix_scope


class SuffixScopeSafetyTests(unittest.TestCase):
    def test_suffix_is_held_for_conflicting_descendant_exact_rule(self):
        rules = RuleIndex([DomainRule("DOMAIN", "api.example.com", "PROXY", 10, "DOMAIN,api.example.com,PROXY")])
        status, _ = inspect_suffix_scope("example.com", "DIRECT", rules, [], {})
        self.assertEqual(status, "CONFLICT")

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


if __name__ == "__main__":
    unittest.main()
