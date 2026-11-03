import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import classify_paths, compute_fingerprint, decide, load_manifest


class ProductionIntentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "automation").mkdir()
        self.manifest_path = self.root / "automation" / "production_inputs.json"
        self.manifest_path.write_text(json.dumps({
            "schema_version": 1,
            "production_input_paths": ["sources/policy.json", "shadowrocket/ss.conf"],
            "non_production_path_patterns": ["reports/**", "rulesets/**", "automation/**", "tests/**"]
        }), encoding="utf-8")
        (self.root / "sources").mkdir()
        (self.root / "sources" / "policy.json").write_text('{"policy":1}', encoding="utf-8")
        (self.root / "shadowrocket").mkdir()
        (self.root / "shadowrocket" / "ss.conf").write_text("[General]", encoding="utf-8")
        self.manifest = load_manifest(self.manifest_path)
        self.now = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.fp = compute_fingerprint(self.root, self.manifest)

    def test_input_change_is_classified_as_production_input(self):
        result = classify_paths(["sources/policy.json"], self.manifest)
        self.assertEqual(result["status"], "INPUT_CHANGED")

    def test_generated_outputs_do_not_create_production_demand(self):
        result = classify_paths(["reports/status.json", "rulesets/direct.list", "automation/task_queue.json"], self.manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")

    def test_unknown_paths_require_review_instead_of_triggering_production(self):
        result = classify_paths(["new/unregistered.py"], self.manifest)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_read_only_user_config_is_a_production_input(self):
        self.assertIn("shadowrocket/ss.conf", self.manifest["production_input_paths"])
        result = classify_paths(["shadowrocket/ss.conf"], self.manifest)
        self.assertEqual(result["status"], "INPUT_CHANGED")

    def test_completion_and_workflow_run_events_never_create_demand(self):
        for event in ("repository_dispatch", "workflow_run"):
            result = decide(event=event, current_fingerprint=self.fp,
                last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
                last_success_at=None, now=self.now)
            self.assertFalse(result["should_produce"])
            self.assertEqual(result["decision"], "OBSERVE_ONLY")

    def test_same_fingerprint_active_task_suppresses_duplicate(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, active_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["decision"], "IN_PROGRESS")
        self.assertFalse(result["should_produce"])

    def test_same_successful_fingerprint_is_satisfied(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["decision"], "ALREADY_SATISFIED")

    def test_schedule_is_due_only_after_explicit_refresh_interval(self):
        due = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=(self.now - timedelta(days=9)).isoformat(), now=self.now)
        not_due = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=(self.now - timedelta(days=2)).isoformat(), now=self.now)
        self.assertEqual(due["decision"], "SCHEDULE_DUE")
        self.assertTrue(due["should_produce"])
        self.assertEqual(not_due["decision"], "ALREADY_SATISFIED")

    def test_unknown_path_blocks_production_even_when_fingerprint_differs(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"REVIEW_REQUIRED"},
            last_success_at=None, now=self.now)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertFalse(result["should_produce"])


if __name__ == "__main__":
    unittest.main()
