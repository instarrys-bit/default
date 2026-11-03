import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import classify_paths, compute_fingerprint, compute_output_fingerprint, decide, load_manifest


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
        (self.root / "rulesets").mkdir()
        for name, body in (("direct.list", "DIRECT\\n"), ("proxy.list", "PROXY\\n"), ("reject.list", "REJECT\\n")):
            (self.root / "rulesets" / name).write_text(body, encoding="utf-8")

    def test_read_only_dashboard_paths_are_non_production(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            ".github/workflows/dashboard-pages.yml",
            "dashboard/README.md",
            "dashboard/index.html",
            "dashboard/data.json",
            "scripts/build_dashboard_snapshot.py",
        ]
        result = classify_paths(paths, manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertEqual(result["unknown_changes"], [])
        self.assertEqual(result["non_production_changes"], sorted(paths))

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

    def test_input_change_uses_stable_fingerprint_idempotency_key(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, revision="commit-a", now=self.now)
        self.assertEqual(result["idempotency_key"], f"production:input:{self.fp}:commit-a")

    def test_scheduled_refresh_key_is_scoped_to_last_success_generation(self):
        stamp = (self.now - timedelta(days=9)).isoformat()
        result = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=stamp, successful_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["idempotency_key"], f"production:schedule:{self.fp}:{stamp}")

    def test_reverted_to_previously_successful_fingerprint_rebuilds_on_input_change(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="different", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp},
            revision="commit-a", now=self.now)
        self.assertEqual(result["decision"], "INPUT_CHANGED")
        self.assertTrue(result["should_produce"])
        self.assertEqual(result["idempotency_key"], f"production:input:{self.fp}:commit-a")

    def test_config_a_to_b_to_a_reconciles_even_when_a_was_previously_successful(self):
        config = self.root / "shadowrocket" / "ss.conf"
        config.write_text("[Rule]\\nDOMAIN,alpha.example,DIRECT\\n", encoding="utf-8")
        fingerprint_a = compute_fingerprint(self.root, self.manifest)
        config.write_text("[Rule]\\nDOMAIN,beta.example,PROXY\\n", encoding="utf-8")
        fingerprint_b = compute_fingerprint(self.root, self.manifest)
        self.assertNotEqual(fingerprint_a, fingerprint_b)

        # Revert to A after B was the last successful generation.
        config.write_text("[Rule]\\nDOMAIN,alpha.example,DIRECT\\n", encoding="utf-8")
        fingerprint_reverted = compute_fingerprint(self.root, self.manifest)
        self.assertEqual(fingerprint_reverted, fingerprint_a)
        classification = classify_paths(["shadowrocket/ss.conf"], self.manifest)
        result = decide(
            event="push", current_fingerprint=fingerprint_reverted,
            last_success_fingerprint=fingerprint_b,
            path_classification=classification, last_success_at=self.now.isoformat(),
            successful_fingerprints={fingerprint_a, fingerprint_b},
            revision="revert-commit", now=self.now,
        )
        self.assertEqual(result["decision"], "INPUT_CHANGED")
        self.assertTrue(result["should_produce"])
        self.assertEqual(
            result["idempotency_key"],
            f"production:input:{fingerprint_a}:revert-commit",
        )

    def test_same_revert_revision_is_idempotent_but_later_revert_is_new_work(self):
        args = dict(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="different", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp}, now=self.now)
        first = decide(**args, revision="commit-a")
        replay = decide(**args, revision="commit-a")
        later = decide(**args, revision="commit-b")
        self.assertEqual(first["idempotency_key"], replay["idempotency_key"])
        self.assertNotEqual(first["idempotency_key"], later["idempotency_key"])

    def test_output_fingerprint_covers_all_three_policy_rule_sets(self):
        first = compute_output_fingerprint(self.root)
        (self.root / "rulesets" / "direct.list").write_text("DIRECT\\nexample.com\\n", encoding="utf-8")
        second = compute_output_fingerprint(self.root)
        self.assertNotEqual(first, second)

    def test_manifest_rejects_paths_classified_as_both_input_and_output(self):
        path = self.root / "automation" / "overlap.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "production_input_paths": ["reports/important.json"],
            "non_production_path_patterns": ["reports/**"]
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "also match non-production patterns"):
            load_manifest(path)

    def test_different_active_fingerprint_blocks_a_second_production_task(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, active_fingerprints={"older-active-fingerprint"}, now=self.now)
        self.assertEqual(result["decision"], "WAIT_FOR_ACTIVE")
        self.assertFalse(result["should_produce"])


if __name__ == "__main__":
    unittest.main()
