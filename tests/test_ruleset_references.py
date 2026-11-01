import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_ruleset_references import extract_rule_set_references, inspect

class RuleSetReferenceAuditTests(unittest.TestCase):
    def test_extracts_only_rule_section_references(self):
        config = "[General]\nRULE-SET,ignored.list,DIRECT\n[Rule]\nRULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT\n"
        refs = extract_rule_set_references(config)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["policy"], "DIRECT")

    def test_policy_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("direct.list", "proxy.list", "reject.list"):
                (root / name).write_text("", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 0, "PROXY": 0, "REJECT": 0}}
            config = "\n".join([
                "[Rule]",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT",
            ])
            report = inspect(config, manifest, root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("expected DIRECT" in x for x in report["errors"]))

    def test_all_three_references_and_file_counts_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("direct.list", "proxy.list", "reject.list"):
                (root / name).write_text("", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 0, "PROXY": 0, "REJECT": 0}}
            config = "\n".join([
                "[Rule]",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT",
            ])
            report = inspect(config, manifest, root)
            self.assertTrue(report["passed"], report["errors"])

if __name__ == "__main__":
    unittest.main()
