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

    def test_untrusted_host_and_wrong_path_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("direct.list", "proxy.list", "reject.list"):
                (root / name).write_text("", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 0, "PROXY": 0, "REJECT": 0}}
            config = "\n".join([
                "[Rule]",
                "RULE-SET,https://example.com/other/direct.list,DIRECT",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT",
            ])
            report = inspect(config, manifest, root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("host must be raw.githubusercontent.com" in x for x in report["errors"]))
            self.assertTrue(any("outside this repository" in x for x in report["errors"]))

    def test_duplicate_reference_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("direct.list", "proxy.list", "reject.list"):
                (root / name).write_text("", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 0, "PROXY": 0, "REJECT": 0}}
            direct = "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT"
            config = "\n".join(["[Rule]", direct, direct,
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT"])
            report = inspect(config, manifest, root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("duplicate RULE-SET URL" in x for x in report["errors"]))


    def test_cross_file_policy_conflict_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "direct.list").write_text("DOMAIN,shared.example\\n", encoding="utf-8")
            (root / "proxy.list").write_text("DOMAIN,shared.example\\n", encoding="utf-8")
            (root / "reject.list").write_text("", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 1, "PROXY": 1, "REJECT": 0}}
            config = "\\n".join([
                "[Rule]",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT",
            ])
            report = inspect(config, manifest, root)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["cross_policy_conflicts"]), 1)

    def test_same_policy_cross_file_duplicate_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "direct.list").write_text("DOMAIN,shared.example\\n", encoding="utf-8")
            (root / "proxy.list").write_text("", encoding="utf-8")
            (root / "reject.list").write_text("DOMAIN,shared.example\\n", encoding="utf-8")
            manifest = {"outputs": ["direct.list", "proxy.list", "reject.list"], "rule_count": {"DIRECT": 1, "PROXY": 0, "REJECT": 1}}
            config = "\\n".join([
                "[Rule]",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/direct.list,DIRECT",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/proxy.list,PROXY",
                "RULE-SET,https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/reject.list,REJECT",
            ])
            report = inspect(config, manifest, root)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["cross_file_duplicates"]), 1)
            self.assertEqual(len(report["cross_policy_conflicts"]), 1)

if __name__ == "__main__":
    unittest.main()
