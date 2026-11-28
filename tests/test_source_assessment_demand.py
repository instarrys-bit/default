import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from source_assessment_demand import assessment_backlog_demand


CURSOR = "https://raw.githubusercontent.com/example/rules/main/list.conf"
DISCOVERY = "a" * 64


def manifest(pending=12, cursor=CURSOR, fingerprint=DISCOVERY):
    return {"metadata": {"pending_assessment_count": pending,
                         "discovery_fingerprint": fingerprint,
                         "latest_assessment": {"next_cursor_url": cursor}}}


def queue(*tasks):
    return {"tasks": list(tasks)}


class AssessmentBacklogDemandTests(unittest.TestCase):
    def test_zero_backlog_is_clear(self):
        self.assertEqual(assessment_backlog_demand(manifest(0), queue())["action"], "clear")

    def test_pending_backlog_creates_cursor_scoped_idempotent_demand(self):
        result = assessment_backlog_demand(manifest(), queue())
        self.assertEqual(result["action"], "enqueue")
        self.assertIn("source-assessment:cursor:", result["idempotency_key"])
        self.assertEqual(result["pending_assessment_count"], 12)

    def test_same_cursor_queued_task_is_not_duplicated(self):
        demand = assessment_backlog_demand(manifest(), queue())
        task = {"idempotency_key": demand["idempotency_key"], "status": "QUEUED"}
        self.assertEqual(assessment_backlog_demand(manifest(), queue(task))["action"], "already_queued")

    def test_same_cursor_terminal_task_stops_infinite_replay(self):
        demand = assessment_backlog_demand(manifest(), queue())
        task = {"task_id": "task-1", "idempotency_key": demand["idempotency_key"], "status": "SUCCEEDED"}
        result = assessment_backlog_demand(manifest(), queue(task))
        self.assertEqual(result["action"], "stalled")
        self.assertEqual(result["task_id"], "task-1")

    def test_cursor_advance_creates_new_batch_identity(self):
        first = assessment_backlog_demand(manifest(), queue())
        second = assessment_backlog_demand(manifest(cursor=CURSOR + "?page=2"), queue())
        self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])

    def test_discovery_change_creates_new_batch_identity(self):
        first = assessment_backlog_demand(manifest(), queue())
        second = assessment_backlog_demand(manifest(fingerprint="b" * 64), queue())
        self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])

    def test_invalid_cursor_fails_closed(self):
        result = assessment_backlog_demand(manifest(cursor="https://evil.example/x/y/z"), queue())
        self.assertEqual(result["action"], "blocked")

    def test_invalid_discovery_fingerprint_fails_closed(self):
        result = assessment_backlog_demand(manifest(fingerprint="bad"), queue())
        self.assertEqual(result["action"], "blocked")

    def test_malformed_pending_count_fails_closed(self):
        with self.assertRaises(ValueError):
            assessment_backlog_demand(manifest(pending=True), queue())


    def test_watchdog_integrates_cursor_scoped_recovery_task(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        scheduler = (root / "scripts/task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("scripts/source_assessment_demand.py", workflow)
        self.assertIn("source-assessment:cursor:", (root / "scripts/source_assessment_demand.py").read_text(encoding="utf-8"))
        self.assertIn("INPUT_CHANGED|SCHEDULE_DUE|RECOVERY_REQUIRED", workflow)
        self.assertIn('"RECOVERY_REQUIRED"', scheduler)
        self.assertIn("assert_current_production_input", scheduler)

    def test_manifest_backlog_missing_cursor_fails_closed(self):
        result = assessment_backlog_demand(manifest(cursor=None), queue())
        self.assertEqual(result["action"], "blocked")

    def test_changed_cursor_does_not_replay_prior_terminal_batch(self):
        first = assessment_backlog_demand(manifest(), queue())
        prior = {"idempotency_key": first["idempotency_key"], "status": "SUCCEEDED"}
        result = assessment_backlog_demand(manifest(cursor=CURSOR + "?next"), queue(prior))
        self.assertEqual(result["action"], "enqueue")


if __name__ == "__main__":
    unittest.main()
