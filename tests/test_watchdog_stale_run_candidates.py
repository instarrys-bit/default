import unittest
from datetime import datetime, timedelta, timezone

from scripts.watchdog_stale_run_candidates import stale_candidates


class WatchdogStaleRunCandidateTests(unittest.TestCase):
    def test_selects_only_superseded_or_timed_out_main_runs(self):
        now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        payload = {
            "workflow_runs": [
                {"id": 1, "status": "in_progress", "head_branch": "main", "head_sha": "old"},
                {
                    "id": 2,
                    "status": "in_progress",
                    "head_branch": "main",
                    "head_sha": "current",
                    "run_started_at": (now - timedelta(hours=7)).isoformat(),
                },
                {
                    "id": 3,
                    "status": "in_progress",
                    "head_branch": "main",
                    "head_sha": "current",
                    "run_started_at": (now - timedelta(hours=1)).isoformat(),
                },
                {"id": 4, "status": "completed", "head_branch": "main", "head_sha": "old"},
                {"id": 5, "status": "in_progress", "head_branch": "feature", "head_sha": "old"},
            ]
        }
        self.assertEqual(
            stale_candidates(payload, "current", now=now),
            [("1", "superseded", "old"), ("2", "timeout", "current")],
        )

    def test_missing_timestamps_and_ids_are_ignored(self):
        payload = {
            "workflow_runs": [
                {"status": "in_progress", "head_branch": "main", "head_sha": "current"},
                {"id": 6, "status": "in_progress", "head_branch": "main", "head_sha": "current"},
            ]
        }
        self.assertEqual(stale_candidates(payload, "current"), [])


if __name__ == "__main__":
    unittest.main()
