import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_dashboard_snapshot import build_candidate_review_metrics, build_task_stage_metrics, build_combined_task_runtime_metrics, watchdog_schedule


class WatchdogScheduleDashboardTests(unittest.TestCase):
    WORKFLOW = """on:
  schedule:
    - cron: "0 * * * *"
    - cron: "30 22 * * *"
"""

    def test_reports_next_hourly_trigger_before_daily_extra_trigger(self):
        now = datetime(2026, 11, 4, 21, 50, tzinfo=timezone.utc)
        result = watchdog_schedule(self.WORKFLOW, now)
        self.assertEqual(result["next_scheduled_trigger_at"], "2026-11-04T22:00:00+00:00")
        self.assertEqual(result["schedule_state"], "known")

    def test_reports_daily_extra_trigger_when_it_is_next(self):
        now = datetime(2026, 11, 4, 22, 10, tzinfo=timezone.utc)
        result = watchdog_schedule(self.WORKFLOW, now)
        self.assertEqual(result["next_scheduled_trigger_at"], "2026-11-04T22:30:00+00:00")

    def test_returns_next_hour_after_daily_trigger_has_passed(self):
        now = datetime(2026, 11, 4, 22, 40, tzinfo=timezone.utc)
        result = watchdog_schedule(self.WORKFLOW, now)
        self.assertEqual(result["next_scheduled_trigger_at"], "2026-11-04T23:00:00+00:00")

    def test_reports_next_quarter_hour_watchdog_trigger(self):
        schedule = """on:
  schedule:
    - cron: "*/15 * * * *"
"""
        now = datetime(2026, 11, 4, 22, 10, tzinfo=timezone.utc)
        result = watchdog_schedule(schedule, now)
        self.assertEqual(result["next_scheduled_trigger_at"], "2026-11-04T22:15:00+00:00")
        self.assertEqual(result["schedule_state"], "known")

    def test_unknown_cron_fails_closed(self):
        unsupported = """on:
  schedule:
    - cron: "*/5 * * * *"
"""
        result = watchdog_schedule(unsupported, datetime(2026, 11, 4, 22, 10, tzinfo=timezone.utc))
        self.assertIsNone(result["next_scheduled_trigger_at"])
        self.assertEqual(result["schedule_state"], "unsupported_cron")

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            watchdog_schedule(self.WORKFLOW, datetime(2026, 11, 4, 22, 10))


class PipelineTaskDashboardMetricsTests(unittest.TestCase):
    def test_reports_discovery_and_assessment_task_states_separately(self):
        tasks = [
            {"target_program_id": "workflow_source_discovery", "status": "SUCCEEDED", "updated_at": "2026-11-08T01:00:00Z"},
            {"target_program_id": "workflow_source_discovery", "status": "QUEUED"},
            {"target_program_id": "script_assess_sources", "status": "CLAIMED"},
            {"target_program_id": "workflow_auto_sync", "status": "DEAD_LETTER"},
        ]
        discovery = build_task_stage_metrics(tasks, "workflow_source_discovery")
        assessment = build_task_stage_metrics(tasks, "script_assess_sources")
        self.assertEqual(discovery["total"], 2)
        self.assertEqual(discovery["by_status"], {"SUCCEEDED": 1, "QUEUED": 1})
        self.assertEqual(assessment["by_status"], {"CLAIMED": 1})
        self.assertEqual(discovery["last_task_at"], "2026-11-08T01:00:00Z")


class CombinedTaskRuntimeDashboardMetricsTests(unittest.TestCase):
    def test_combines_production_discovery_and_assessment_lanes(self):
        tasks = [
            {"target_program_id": "workflow_auto_sync", "status": "SUCCEEDED"},
            {"target_program_id": "workflow_auto_sync", "status": "DEAD_LETTER"},
            {"target_program_id": "workflow_source_discovery", "status": "SUCCEEDED"},
            {"target_program_id": "workflow_source_discovery", "status": "QUEUED"},
            {"target_program_id": "script_assess_sources", "status": "CLAIMED"},
            {"target_program_id": "unrelated_program", "status": "CLAIMED"},
        ]
        result = build_combined_task_runtime_metrics(
            tasks, ("workflow_auto_sync", "workflow_source_discovery", "script_assess_sources")
        )
        self.assertEqual(result, {
            "total": 5,
            "by_status": {"SUCCEEDED": 2, "DEAD_LETTER": 1, "QUEUED": 1, "CLAIMED": 1},
            "active": 2,
            "succeeded": 2,
            "dead_letter": 1,
            "cancelled": 0,
        })


class CandidateReviewDashboardMetricsTests(unittest.TestCase):
    def test_distinguishes_candidate_pool_from_unreviewed_candidates(self):
        candidates = [
            {"domain": "seen.example", "classification": "DIRECT"},
            {"domain": "new.example", "classification": "PROXY"},
            {"domain": "SEEN.example.", "classification": "DIRECT"},
        ]
        reviews = [
            {"domain": "seen.example", "status": "REVIEW"},
            {"domain": "historical-only.example", "status": "APPROVED"},
        ]
        result = build_candidate_review_metrics(
            candidates, reviews, {"status": "complete", "candidate_count": 2}, "2026-11-04T00:00:00Z"
        )
        self.assertEqual(result["candidate_total"], 2)
        self.assertEqual(result["history_recorded"], 1)
        self.assertEqual(result["missing_history"], 1)
        self.assertEqual(result["status_counts"], {"REVIEW": 1, "UNREVIEWED": 1})
        self.assertEqual(result["review_ledger_total"], 2)
        self.assertEqual(result["cursor_status"], "complete")

    def test_empty_inputs_are_zero_not_inferred(self):
        result = build_candidate_review_metrics([], [], {})
        self.assertEqual(result["candidate_total"], 0)
        self.assertEqual(result["history_recorded"], 0)
        self.assertEqual(result["missing_history"], 0)
        self.assertEqual(result["status_counts"], {})


if __name__ == "__main__":
    unittest.main()
