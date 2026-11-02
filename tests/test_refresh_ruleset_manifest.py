import json
import tempfile
import unittest
from pathlib import Path

from refresh_ruleset_manifest import refresh


class RefreshRulesetManifestTests(unittest.TestCase):
    def make_root(self, counts=None):
        root = Path(tempfile.mkdtemp())
        rules = root / "rulesets"
        rules.mkdir()
        manifest = {
            "schema_version": 2,
            "outputs": ["direct.list", "proxy.list", "reject.list"],
            "rule_lifecycle": {},
        }
        if counts is not None:
            manifest["rule_count"] = counts
        (rules / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (rules / "direct.list").write_text("DOMAIN,one.example\n", encoding="utf-8")
        (rules / "proxy.list").write_text("DOMAIN,two.example\nDOMAIN-SUFFIX,three.example\n", encoding="utf-8")
        (rules / "reject.list").write_text("", encoding="utf-8")
        return root

    def test_repairs_missing_or_stale_counts_from_final_rule_files(self):
        root = self.make_root()
        result = refresh(root)
        manifest = json.loads((root / "rulesets/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(result["rule_count"], {"DIRECT": 1, "PROXY": 2, "REJECT": 0})
        self.assertEqual(manifest["rule_count"], result["rule_count"])
        self.assertEqual(manifest["published_rule_total"], 3)
        self.assertEqual(manifest["rule_lifecycle"]["PROXY"]["current_count"], 2)

    def test_rejects_malformed_rule_without_rewriting_manifest(self):
        root = self.make_root({"DIRECT": 1, "PROXY": 2, "REJECT": 0})
        path = root / "rulesets/reject.list"
        path.write_text("not-a-rule\n", encoding="utf-8")
        before = (root / "rulesets/manifest.json").read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            refresh(root)
        self.assertEqual((root / "rulesets/manifest.json").read_text(encoding="utf-8"), before)

    def test_rejects_combined_count_above_hard_cap_without_truncation(self):
        root = self.make_root()
        path = root / "rulesets/reject.list"
        path.write_text("".join(f"DOMAIN,d{i}.example\n" for i in range(30_001)), encoding="utf-8")
        before = (root / "rulesets/manifest.json").read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            refresh(root)
        self.assertEqual((root / "rulesets/manifest.json").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
