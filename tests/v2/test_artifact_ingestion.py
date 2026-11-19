import datetime
import io
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from ingest_actions_artifacts import download_artifact_zip, scan_recent_runs


class ArtifactIngestionPollingTests(unittest.TestCase):
    def test_artifact_redirect_does_not_forward_github_bearer_token(self):
        class RedirectOpener:
            def __init__(self):
                self.request = None

            def open(self, request, timeout):
                self.request = request
                raise urllib.error.HTTPError(
                    request.full_url, 302, "Found",
                    {"Location": "https://blob.example/signed-artifact.zip"},
                    io.BytesIO(),
                )

        opener = RedirectOpener()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"zip-bytes"
        response.__enter__.return_value.headers.get.return_value = "application/zip"
        with patch("ingest_actions_artifacts.urllib.request.build_opener", return_value=opener), patch(
            "ingest_actions_artifacts.urllib.request.urlopen", return_value=response
        ) as urlopen:
            payload, mime = download_artifact_zip(
                "https://api.github.com/repos/instarrys-bit/default/actions/artifacts/1/zip",
                "secret-token",
            )

        self.assertEqual(payload, b"zip-bytes")
        self.assertEqual(mime, "application/zip")
        self.assertEqual(opener.request.headers.get("Authorization"), "Bearer secret-token")
        redirected_request = urlopen.call_args.args[0]
        self.assertNotIn("Authorization", redirected_request.headers)

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
