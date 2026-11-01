import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_config_drift import compare_sections, parse_config


class ConfigDriftTests(unittest.TestCase):
    def test_parser_reads_sections_and_repeated_values(self):
        parsed = parse_config("[General]\\ndns-server = one\\ndns-server = two\\n[MITM]\\nenable = true\\n")
        self.assertEqual(parsed["General"]["dns-server"], ["one", "two"])
        self.assertEqual(parsed["MITM"]["enable"], ["true"])

    def test_compare_detects_dns_change_and_added_mitm(self):
        baseline = parse_config("[General]\\ndns-server = old\\n[Rule]\\n")
        managed = parse_config("[General]\\ndns-server = new\\n[MITM]\\nenable = true\\n")
        changes = compare_sections(baseline, managed)
        self.assertTrue(any(x["section"] == "General" and x["key"] == "dns-server" for x in changes))
        self.assertTrue(any(x["kind"] == "added_section" and x["section"] == "MITM" for x in changes))


if __name__ == "__main__":
    unittest.main()
