import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from register_unclassified_paths import register_paths


class WatchdogRegistrationTests(unittest.TestCase):
    def test_new_unknown_paths_enter_pending_inbox_without_approval(self):
        ledger = {"schema_version": 1, "entries": []}
        result = register_paths(
            ["dashboard/index.html", "scripts/new_tool.py"],
            ledger, event="push", revision="abc123", run_id="42",
            run_url="https://github.com/example/repo/actions/runs/42",
            now="2026-11-04T00:00:00Z",
        )
        self.assertEqual(len(result["entries"]), 2)
        self.assertTrue(all(x["status"] == "PENDING_CLASSIFICATION" for x in result["entries"]))

    def test_repeat_observation_is_deduplicated_and_counted(self):
        ledger = {"schema_version": 1, "entries": []}
        args = dict(event="push", revision="abc123", run_id="42",
                    run_url="https://example.test/run", now="2026-11-04T00:00:00Z")
        register_paths(["dashboard/index.html"], ledger, **args)
        register_paths(["dashboard/index.html", "dashboard/index.html"], ledger, **args)
        self.assertEqual(len(ledger["entries"]), 1)
        self.assertEqual(ledger["entries"][0]["seen_count"], 2)

    def test_registration_does_not_overwrite_existing_classification(self):
        ledger = {"schema_version": 1, "entries": [{
            "path": "dashboard/index.html", "status": "NON_PRODUCTION",
            "first_seen_at": "2026-11-01T00:00:00Z", "last_seen_at": "2026-11-01T00:00:00Z",
            "seen_count": 1,
        }]}
        register_paths(["dashboard/index.html"], ledger, event="push", revision="def456",
                       run_id="43", run_url="https://example.test/run",
                       now="2026-11-04T00:00:00Z")
        self.assertEqual(ledger["entries"][0]["status"], "NON_PRODUCTION")
        self.assertEqual(ledger["entries"][0]["seen_count"], 2)

    def test_rejects_paths_that_escape_repository(self):
        ledger = {"schema_version": 1, "entries": []}
        with self.assertRaises(ValueError):
            register_paths(["../outside"], ledger, event="push", revision="abc",
                           run_id="1", run_url="https://example.test")


if __name__ == "__main__":
    unittest.main()
