import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_config_drift import build_report, git_blob_sha, parse_config


class ConfigBaselineTests(unittest.TestCase):
    def test_parser_reads_sections_and_repeated_values(self):
        parsed = parse_config("[General]\ndns-server = one\ndns-server = two\n[MITM]\nenable = true\n")
        self.assertEqual(parsed["General"]["dns-server"], ["one", "two"])
        self.assertEqual(parsed["MITM"]["enable"], ["true"])

    def test_parser_preserves_commas_in_rule_and_rewrite_lines(self):
        parsed = parse_config("[Rule]\nURL-REGEX,^http://host/(a,b),REJECT\n[URL Rewrite]\n^http://host/a,b _ reject\n")
        self.assertEqual(parsed["Rule"]["__raw_lines__"], ["URL-REGEX,^http://host/(a,b),REJECT"])
        self.assertEqual(parsed["URL Rewrite"]["__raw_lines__"], ["^http://host/a,b _ reject"])

    def test_current_config_is_authority_and_dns_mitm_are_observations(self):
        content = b"[General]\ndns-server = quad9\n[Rule]\nDOMAIN,example.com,DIRECT\n[MITM]\nenable = true\n"
        report = build_report(content, git_blob_sha(content), "shadowrocket/ss.conf")
        self.assertTrue(report["baseline_matches_registered_blob"])
        self.assertEqual(report["baseline_path"], "shadowrocket/ss.conf")
        self.assertEqual(report["dns_snapshot"]["dns-server"], ["quad9"])
        self.assertTrue(report["mitm_enabled"])
        self.assertEqual(report["rule_line_count"], 1)

    def test_unregistered_config_change_is_detected(self):
        content = b"[General]\ndns-server = changed\n"
        report = build_report(content, "not-the-current-sha", "shadowrocket/ss.conf")
        self.assertFalse(report["baseline_matches_registered_blob"])


if __name__ == "__main__":
    unittest.main()
