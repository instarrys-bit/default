import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_config import validate


def config_with_rule(rule):
    return "[General]\nloglevel = warning\n[Rule]\n" + rule + "\n[Host]\n"


class DomainWildcardRuleTests(unittest.TestCase):
    def validate_rule(self, rule):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.conf"
            path.write_text(config_with_rule(rule), encoding="utf-8")
            return validate(path)

    def test_accepts_user_domain_wildcard_rule(self):
        self.assertEqual(
            self.validate_rule("DOMAIN-WILDCARD,apmplus-*.volces.com,REJECT"),
            [],
        )

    def test_rejects_domain_wildcard_without_wildcard(self):
        errors = self.validate_rule("DOMAIN-WILDCARD,apmplus.volces.com,REJECT")
        self.assertTrue(any("invalid domain wildcard pattern" in error[1] for error in errors))

    def test_rejects_malformed_domain_wildcard(self):
        errors = self.validate_rule("DOMAIN-WILDCARD,apmplus-*.volces..com,REJECT")
        self.assertTrue(any("invalid domain wildcard pattern" in error[1] for error in errors))

    def test_rejects_invalid_domain_wildcard_policy(self):
        errors = self.validate_rule("DOMAIN-WILDCARD,apmplus-*.volces.com,INVALID")
        self.assertTrue(any("invalid domain wildcard policy" in error[1] for error in errors))


if __name__ == "__main__":
    unittest.main()
