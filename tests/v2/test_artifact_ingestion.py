import datetime
import os
import unittest
from unittest.mock import patch

from ingest_actions_artifacts import scan_recent_runs


class ArtifactIngestionPollingTests(unittest.TestCase):
    def test_polling_dispatches_only_completed_main_auto_sync_and_watchdog_runs(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        artifacts = [
            {"id": 1, "created_at": now, "workflow_run": {"id": 101, "head_branch": "main"}},
            {"id": 2, "created_at": now, "workflow_run": {"id": 102, "head_branch": "feature"}},
            {"id": 3, "created_at": now, "workflow_run": {"id": 103, "head_branch": "main"}},
            {"id": 4, "created_at": now, "workflow_run": {"id": 104, "head_branch": "main"}},
        ]

        def fake_get_json(url, token):
            if "/actions/artifacts?" in url:
                return {"artifacts": artifacts if "page=1" in url else []}
            if url.endswith("/actions/runs/101"):
                return {"status": "completed", "head_branch": "main", "path": ".github/workflows/auto_sync.yml"}
            if url.endswith("/actions/runs/103"):
                return {"status": "in_progress", "head_branch": "main", "path": ".github/workflows/auto_sync.yml"}
            if url.endswith("/actions/runs/104"):
                return {"status": "completed", "head_branch": "main", "path": ".github/workflows/dashboard-pages.yml"}
            raise AssertionError(url)

        with patch("ingest_actions_artifacts.get_json", side_effect=fake_get_json), patch(
            "ingest_actions_artifacts.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            result = scan_recent_runs("owner/repo", "token")

        self.assertEqual(result, 0)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["env"]["SOURCE_RUN_ID"], "101")

    def test_polling_reports_failed_ingestion_without_claiming_success(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        artifacts = [{"id": 1, "created_at": now, "workflow_run": {"id": 201, "head_branch": "main"}}]

        def fake_get_json(url, token):
            if "/actions/artifacts?" in url:
                return {"artifacts": artifacts if "page=1" in url else []}
            if url.endswith("/actions/runs/201"):
                return {"status": "completed", "head_branch": "main", "path": ".github/workflows/automation-watchdog.yml"}
            raise AssertionError(url)

        with patch("ingest_actions_artifacts.get_json", side_effect=fake_get_json), patch(
            "ingest_actions_artifacts.subprocess.run"
        ) as run:
            run.return_value.returncode = 2
            result = scan_recent_runs("owner/repo", "token")

        self.assertEqual(result, 1)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
