import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog_recovery_policy import decide_recovery


NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def run(run_id, *, minutes_ago, conclusion="timed_out", sha=SHA, branch="main"):
    created = NOW - timedelta(minutes=minutes_ago)
    return {
        "id": run_id,
        "head_branch": branch,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created.isoformat(),
    }


class WatchdogRecoveryPolicyTests(unittest.TestCase):
    def test_first_retry_is_allowed_without_prior_failure(self):
        result = decide_recovery(
            [run(10, minutes_ago=1)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["retry_number"], 1)
        self.assertEqual(result["reason"], "bounded_retry_allowed")

    def test_second_retry_requires_fifteen_minute_cooldown(self):
        result = decide_recovery(
            [run(9, minutes_ago=5)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "cooldown_active")
        self.assertEqual(result["retry_after_seconds"], 600)

        result = decide_recovery(
            [run(9, minutes_ago=20)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["retry_number"], 2)

    def test_third_retry_is_blocked_after_two_prior_retryable_failures(self):
        result = decide_recovery(
            [run(8, minutes_ago=60), run(9, minutes_ago=30)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "retry_limit_reached")

    def test_exponential_cooldown_increases_for_later_retry(self):
        result = decide_recovery(
            [run(8, minutes_ago=20), run(9, minutes_ago=5)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
            max_retries=3,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["cooldown_seconds"], 1800)
        self.assertEqual(result["retry_after_seconds"], 1500)

    def test_other_sha_branch_and_conclusions_do_not_consume_retry_budget(self):
        unrelated = [
            run(1, minutes_ago=5, sha="b" * 40),
            run(2, minutes_ago=5, branch="feature"),
            run(3, minutes_ago=5, conclusion="failure"),
            run(4, minutes_ago=5, conclusion="success"),
            run(5, minutes_ago=5, conclusion="cancelled"),
        ]
        result = decide_recovery(
            unrelated,
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["prior_retryable_failures"], 0)

    def test_old_or_future_runs_do_not_consume_retry_budget(self):
        result = decide_recovery(
            [run(1, minutes_ago=1500), run(2, minutes_ago=-5)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["prior_retryable_failures"], 0)

    def test_source_run_is_not_counted_as_its_own_prior_failure(self):
        result = decide_recovery(
            [run(10, minutes_ago=1)],
            source_run_id="10",
            source_sha=SHA,
            now=NOW,
        )
        self.assertEqual(result["prior_retryable_failures"], 0)


if __name__ == "__main__":
    unittest.main()
