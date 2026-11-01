import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_ruleset_references import extract_rule_set_references, inspect


BASE_URL = "https://raw.githubusercontent.com/instarrys-bit/default/main/rulesets/"


def make_config(order=None, extra_after_sets=""):
    order = order or [
        ("reject.list", "REJECT"),
        ("proxy.list", "PROXY"),
        ("direct.list", "DIRECT"),
    ]
    lines = [
        "[Rule]",
        "# === Layer 1: explicit reject ===",
        "DOMAIN-SUFFIX,ads.example,REJECT",
        "# === Layer 2: explicit rules ===",
        "DOMAIN,manual.example,PROXY",
        "# === Layer 3: domestic domains ===",
        "DOMAIN-SUFFIX,cn.example,DIRECT",
        "# === Layer 4: overseas domains ===",
        "DOMAIN-SUFFIX,global.example,PROXY",
        "# === Layer 5: explicit IP exceptions ===",
        "# --- 5E. final original explicit IP rules ---",
        "IP-CIDR,203.0.113.1/32,PROXY,no-resolve",
        "# --- External Rule Sets: Original Rules First, Then REJECT -> PROXY -> DIRECT ---",
    ]
    lines.extend(f"RULE-SET,{BASE_URL}{filename},{policy}" for filename, policy in order)
    if extra_after_sets:
        lines.append(extra_after_sets)
    lines.extend([
        "# --- 5F-1. ASN/GeoIP fallback begins ---",
        "IP-ASN,13335,PROXY",
        "# --- 5F-2. Mainland China ASN fallback ---",
        "IP-ASN,4134,DIRECT",
        "GEOIP,CN,DIRECT",
        "# === Layer 6: final fallback ===",
        "FINAL,PROXY",
        "[Host]",
    ])
    return "\n".join(lines)


def empty_rulesets(root):
    for name in ("direct.list", "proxy.list", "reject.list"):
        (root / name).write_text("", encoding="utf-8")


def empty_manifest():
    return {
        "outputs": ["direct.list", "proxy.list", "reject.list"],
        "rule_count": {"DIRECT": 0, "PROXY": 0, "REJECT": 0},
    }


class RuleSetReferenceAuditTests(unittest.TestCase):
    def test_extracts_only_rule_section_references(self):
        config = "[General]\nRULE-SET,ignored.list,DIRECT\n" + make_config()
        refs = extract_rule_set_references(config)
        self.assertEqual(len(refs), 3)
        self.assertEqual(
            [(x["url"].rsplit("/", 1)[-1], x["policy"]) for x in refs],
            [("reject.list", "REJECT"), ("proxy.list", "PROXY"), ("direct.list", "DIRECT")],
        )

    def test_expected_order_and_placement_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            report = inspect(make_config(), empty_manifest(), root)
            self.assertTrue(report["passed"], report["errors"])
            self.assertTrue(report["layout"]["passed"])

    def test_wrong_external_priority_order_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            wrong = [
                ("reject.list", "REJECT"),
                ("direct.list", "DIRECT"),
                ("proxy.list", "PROXY"),
            ]
            report = inspect(make_config(wrong), empty_manifest(), root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("REJECT -> PROXY -> DIRECT" in x for x in report["errors"]))

    def test_external_rule_sets_after_geoip_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            config = make_config()
            block = [
                f"RULE-SET,{BASE_URL}reject.list,REJECT",
                f"RULE-SET,{BASE_URL}proxy.list,PROXY",
                f"RULE-SET,{BASE_URL}direct.list,DIRECT",
            ]
            for line in block:
                config = config.replace(line + "\n", "")
            config = config.replace(
                "FINAL,PROXY\n[Host]",
                "\n".join(block) + "\nFINAL,PROXY\n[Host]",
            )
            report = inspect(config, empty_manifest(), root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("before the ASN/GeoIP fallback" in x for x in report["errors"]))

    def test_original_explicit_rule_after_external_block_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            config = make_config(extra_after_sets="DOMAIN,late-manual.example,DIRECT")
            report = inspect(config, empty_manifest(), root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("active routing rules appear between external RULE-SETs" in x for x in report["errors"]))

    def test_policy_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            config = make_config().replace(
                f"RULE-SET,{BASE_URL}direct.list,DIRECT",
                f"RULE-SET,{BASE_URL}direct.list,PROXY",
            )
            report = inspect(config, empty_manifest(), root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("expected DIRECT" in x for x in report["errors"]))

    def test_duplicate_reference_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_rulesets(root)
            config = make_config().replace(
                f"RULE-SET,{BASE_URL}direct.list,DIRECT\n",
                f"RULE-SET,{BASE_URL}direct.list,DIRECT\nRULE-SET,{BASE_URL}direct.list,DIRECT\n",
            )
            report = inspect(config, empty_manifest(), root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("duplicate RULE-SET URL" in x for x in report["errors"]))

    def test_cross_file_policy_conflict_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reject.list").write_text("", encoding="utf-8")
            (root / "proxy.list").write_text("DOMAIN,shared.example\n", encoding="utf-8")
            (root / "direct.list").write_text("DOMAIN,shared.example\n", encoding="utf-8")
            manifest = {
                "outputs": ["direct.list", "proxy.list", "reject.list"],
                "rule_count": {"DIRECT": 1, "PROXY": 1, "REJECT": 0},
            }
            report = inspect(make_config(), manifest, root)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["cross_policy_conflicts"]), 1)

    def test_cross_scope_policy_conflict_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reject.list").write_text("", encoding="utf-8")
            (root / "proxy.list").write_text("DOMAIN-SUFFIX,example.com\n", encoding="utf-8")
            (root / "direct.list").write_text("DOMAIN,api.example.com\n", encoding="utf-8")
            manifest = {
                "outputs": ["direct.list", "proxy.list", "reject.list"],
                "rule_count": {"DIRECT": 1, "PROXY": 1, "REJECT": 0},
            }
            report = inspect(make_config(), manifest, root)
            self.assertFalse(report["passed"])
            self.assertEqual(len(report["cross_policy_conflicts"]), 1)


if __name__ == "__main__":
    unittest.main()
