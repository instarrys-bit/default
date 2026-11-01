import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_ruleset_config_overlap import audit, first_ruleset_line, match_candidate, prior_rule_lines


class RulesetConfigOverlapTests(unittest.TestCase):
    def test_only_rules_before_first_ruleset_are_considered(self):
        config = """[Rule]
DOMAIN,api.example.com,DIRECT
RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY
DOMAIN,late.example.com,REJECT
[Host]
"""
        rules = prior_rule_lines(config)
        self.assertEqual(rules, [(2, "DOMAIN,api.example.com,DIRECT")])
        self.assertEqual(first_ruleset_line(config), 3)

    def test_domain_suffix_uses_dns_label_boundary(self):
        rules = [(2, "DOMAIN-SUFFIX,example.com,DIRECT")]
        self.assertEqual(match_candidate("api.example.com", "DIRECT", rules)["status"], "ALREADY_COVERED")
        self.assertEqual(match_candidate("notexample.com", "DIRECT", rules)["status"], "NOT_COVERED_BY_PRIOR_DOMAIN_RULES")

    def test_conflicting_first_match_is_reported(self):
        rules = [
            (2, "DOMAIN-SUFFIX,example.com,PROXY"),
            (3, "DOMAIN,api.example.com,DIRECT"),
        ]
        result = match_candidate("api.example.com", "DIRECT", rules)
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["line"], 2)

    def test_keyword_and_conditional_are_potential_not_definite(self):
        keyword = match_candidate("api.example.com", "DIRECT", [(2, "DOMAIN-KEYWORD,example,REJECT")])
        self.assertEqual(keyword["status"], "POTENTIAL_MATCH")
        conditional = match_candidate("api.example.com", "DIRECT", [(2, "AND,((DOMAIN-SUFFIX,example.com),(GEOIP,CN)),DIRECT")])
        self.assertEqual(conditional["status"], "CONDITIONAL_POTENTIAL")

    def test_skip_proxy_is_counted_as_direct_coverage(self):
        config = "[General]\nskip-proxy = *.example.com,exact.example.net,192.168.0.0/16\n[Rule]\nRULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT\n[Host]\n"
        ledger = {"reviews": [
            {"domain": "api.example.com", "policy": "PROXY", "status": "REVIEW"},
            {"domain": "exact.example.net", "policy": "DIRECT", "status": "REVIEW"},
            {"domain": "notexample.com", "policy": "DIRECT", "status": "REVIEW"}
        ]}
        report = audit(config, ledger)
        by_domain = {item["domain"]: item for item in report["results"]}
        self.assertEqual(by_domain["api.example.com"]["status"], "CONFLICT")
        self.assertEqual(by_domain["exact.example.net"]["status"], "ALREADY_COVERED")
        self.assertEqual(by_domain["notexample.com"]["status"], "NOT_COVERED_BY_PRIOR_DOMAIN_RULES")

    def test_approved_ledger_overlap_fails_closed(self):
        config = "[General]\nskip-proxy = \n[Rule]\nDOMAIN,api.example.com,REJECT\nRULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT\n[Host]\n"
        ledger = {"reviews": [{"domain": "api.example.com", "policy": "DIRECT", "status": "APPROVED"}]}
        report = audit(config, ledger)
        self.assertFalse(report["passed"])
        self.assertEqual(report["results"][0]["status"], "CONFLICT")

    def test_later_rule_does_not_mark_approved_candidate_as_overlapping(self):
        config = "[General]\nskip-proxy = \n[Rule]\nRULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT\nDOMAIN,api.example.com,REJECT\n[Host]\n"
        ledger = {"reviews": [{"domain": "api.example.com", "policy": "DIRECT", "status": "APPROVED"}]}
        report = audit(config, ledger)
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["results"][0]["status"], "NOT_COVERED_BY_PRIOR_DOMAIN_RULES")


if __name__ == "__main__":
    unittest.main()
