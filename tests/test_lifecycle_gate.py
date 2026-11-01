import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle_gate import count_published_rules, update_lifecycle_state


class LifecycleGateTests(unittest.TestCase):
    def make_rulesets(self, root, count):
        directory = root / "rulesets"
        directory.mkdir(parents=True)
        for name in ("direct", "proxy", "reject"):
            (directory / (name + ".list")).write_text("", encoding="utf-8")
        for index in range(count):
            name = ("direct", "proxy", "reject")[index % 3]
            path = directory / (name + ".list")
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"DOMAIN,d{index}.example\n")

    def test_threshold_is_total_published_rules_not_daily_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 4999)
            state = update_lifecycle_state(root, "2026-11-01T00:00:00+00:00")
            self.assertEqual(count_published_rules(root), 4999)
            self.assertFalse(state["active"])
            self.make_rulesets(root, 5000)
            state = update_lifecycle_state(root, "2026-11-02T00:00:00+00:00")
            self.assertTrue(state["active"])
            self.assertEqual(state["published_rule_count"], 5000)

    def test_activation_remains_latched_after_total_falls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 5000)
            first = update_lifecycle_state(root, "2026-11-01T00:00:00+00:00")
            self.make_rulesets(root, 10)
            second = update_lifecycle_state(root, "2026-11-02T00:00:00+00:00")
            self.assertTrue(first["active"])
            self.assertTrue(second["active"])
            self.assertEqual(second["activated_at"], first["activated_at"])

    def test_rejects_unexpected_rule_set_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 0)
            (root / "rulesets" / "extra.list").write_text("DOMAIN,x.example\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                count_published_rules(root)


if __name__ == "__main__":
    unittest.main()
