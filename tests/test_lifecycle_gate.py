import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle_gate import count_published_rules, update_lifecycle_state, complete_lifecycle_review


class LifecycleGateTests(unittest.TestCase):
    def make_rulesets(self, root, count):
        directory = root / "rulesets"
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("direct", "proxy", "reject"):
            (directory / (name + ".list")).write_text("", encoding="utf-8")
        for index in range(count):
            name = ("direct", "proxy", "reject")[index % 3]
            with (directory / (name + ".list")).open("a", encoding="utf-8") as stream:
                stream.write(f"DOMAIN,d{index}.example\n")

    def test_each_5000_published_addition_milestone_is_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 4999)
            state = update_lifecycle_state(root, "2026-11-01T00:00:00+00:00")
            self.assertEqual(count_published_rules(root), 4999)
            self.assertEqual(state["due_milestones"], [])
            self.make_rulesets(root, 5000)
            state = update_lifecycle_state(root, "2026-11-02T00:00:00+00:00")
            self.assertEqual(state["due_milestones"], [5000])
            # A failed audit must leave the milestone pending.
            state = update_lifecycle_state(root, "2026-11-03T00:00:00+00:00")
            self.assertEqual(state["due_milestones"], [5000])
            complete_lifecycle_review(root, "2026-11-03T00:01:00+00:00")
            self.make_rulesets(root, 9999)
            state = update_lifecycle_state(root, "2026-11-04T00:00:00+00:00")
            self.assertEqual(state["due_milestones"], [])
            self.make_rulesets(root, 10000)
            state = update_lifecycle_state(root, "2026-11-05T00:00:00+00:00")
            self.assertEqual(state["due_milestones"], [10000])

    def test_multiple_crossed_milestones_are_not_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 16000)
            state = update_lifecycle_state(root, "2026-11-01T00:00:00+00:00")
            self.assertEqual(state["due_milestones"], [5000, 10000, 15000])

    def test_monthly_audit_only_starts_at_30000_and_repeats_after_30_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 29999)
            state = update_lifecycle_state(root, "2026-11-01T00:00:00+00:00")
            self.assertFalse(state["monthly_review_due"])
            self.make_rulesets(root, 30000)
            state = update_lifecycle_state(root, "2026-11-02T00:00:00+00:00")
            self.assertTrue(state["monthly_review_due"])
            complete_lifecycle_review(root, "2026-11-02T00:00:00+00:00")
            state = update_lifecycle_state(root, "2026-12-01T00:00:00+00:00")
            self.assertFalse(state["monthly_review_due"])
            state = update_lifecycle_state(root, "2026-12-02T00:00:00+00:00")
            self.assertTrue(state["monthly_review_due"])

    def test_rejects_unexpected_rule_set_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_rulesets(root, 0)
            (root / "rulesets" / "extra.list").write_text("DOMAIN,x.example\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                count_published_rules(root)


if __name__ == "__main__":
    unittest.main()
