import datetime
import io
import json
from contextlib import redirect_stdout
import unittest
import urllib.error
import subprocess
from unittest.mock import MagicMock, patch

from ingest_actions_artifacts import MAX_SEGMENT_BYTES, download_artifact_zip, iter_archive_segments, scan_recent_runs


class ArtifactIngestionPollingTests(unittest.TestCase):

    def test_artifact_archive_segments_stay_within_40mb_storage_cap(self):
        self.assertEqual(MAX_SEGMENT_BYTES, 40_000_000)
        segments = list(iter_archive_segments(b"0123456789", max_segment_bytes=4))
        self.assertEqual(segments, [(0, b"0123"), (1, b"4567"), (2, b"89")])
        self.assertTrue(all(len(segment) <= MAX_SEGMENT_BYTES for _, segment in segments))
        with self.assertRaises(ValueError):
            list(iter_archive_segments(b"data", max_segment_bytes=0))

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

    def test_artifact_blob_download_retries_transient_503(self):
        class RedirectOpener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url, 302, "Found",
                    {"Location": "https://blob.example/signed-artifact.zip"},
                    io.BytesIO(),
                )

        opener = RedirectOpener()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"zip-bytes"
        response.__enter__.return_value.headers.get.return_value = "application/zip"
        transient = urllib.error.HTTPError(
            "https://blob.example/signed-artifact.zip", 503, "Server Busy",
            {"Retry-After": "0"}, io.BytesIO(),
        )
        with patch("ingest_actions_artifacts.urllib.request.build_opener", return_value=opener), patch(
            "ingest_actions_artifacts.urllib.request.urlopen", side_effect=[transient, response]
        ) as urlopen, patch("ingest_actions_artifacts.time.sleep"):
            payload, mime = download_artifact_zip(
                "https://api.github.com/repos/owner/repo/actions/artifacts/1/zip",
                "token",
            )
        self.assertEqual(payload, b"zip-bytes")
        self.assertEqual(mime, "application/zip")
        self.assertEqual(urlopen.call_count, 2)


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
            if url.endswith("/actions/runs/102"):
                return {"status": "completed", "head_branch": "feature", "path": ".github/workflows/auto_sync.yml"}
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

    def test_polling_bounds_each_scan_after_filtering_unrelated_runs(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        artifacts = [
            {"id": 1, "created_at": now, "workflow_run": {"id": 301, "head_branch": "main"}},
            {"id": 2, "created_at": now, "workflow_run": {"id": 302, "head_branch": "main"}},
            {"id": 3, "created_at": now, "workflow_run": {"id": 303, "head_branch": "main"}},
            {"id": 4, "created_at": now, "workflow_run": {"id": 304, "head_branch": "main"}},
        ]

        def fake_get_json(url, token):
            if "/actions/artifacts?" in url:
                return {"artifacts": artifacts if "page=1" in url else []}
            run_id = int(url.rsplit("/", 1)[-1])
            path = ".github/workflows/dashboard-pages.yml" if run_id in (301, 302) else ".github/workflows/auto_sync.yml"
            return {"status": "completed", "head_branch": "main", "path": path}

        output = io.StringIO()
        with patch("ingest_actions_artifacts.get_json", side_effect=fake_get_json), patch(
            "ingest_actions_artifacts.subprocess.run"
        ) as run, patch("ingest_actions_artifacts.MAX_RUNS_PER_SCAN", 2), redirect_stdout(output):
            run.return_value.returncode = 0
            result = scan_recent_runs("owner/repo", "token")

        self.assertEqual(result, 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([call.kwargs["env"]["SOURCE_RUN_ID"] for call in run.call_args_list], ["303", "304"])
        summary = json.loads(output.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["candidate_run_count"], 4)
        self.assertEqual(summary["eligible_run_count"], 2)
        self.assertEqual(summary["selected_run_count"], 2)
        self.assertEqual(summary["deferred_run_count"], 0)

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


    def test_polling_bounds_each_run_and_continues_after_a_timed_out_run(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        artifacts = [
            {"id": 1, "created_at": now, "workflow_run": {"id": 401, "head_branch": "main"}},
            {"id": 2, "created_at": now, "workflow_run": {"id": 402, "head_branch": "main"}},
        ]

        def fake_get_json(url, token):
            if "/actions/artifacts?" in url:
                return {"artifacts": artifacts if "page=1" in url else []}
            run_id = int(url.rsplit("/", 1)[-1])
            return {
                "status": "completed",
                "head_branch": "main",
                "path": ".github/workflows/auto_sync.yml",
            }

        output = io.StringIO()
        timeout = __import__("subprocess").TimeoutExpired(
            cmd=["python", "ingest_actions_artifacts.py"], timeout=600
        )
        completed = __import__("subprocess").CompletedProcess(args=["python"], returncode=0)
        with patch("ingest_actions_artifacts.get_json", side_effect=fake_get_json), patch(
            "ingest_actions_artifacts.subprocess.run", side_effect=[timeout, completed]
        ) as run, patch("ingest_actions_artifacts.MAX_RUNS_PER_SCAN", 2), redirect_stdout(output):
            result = scan_recent_runs("owner/repo", "token")

        self.assertEqual(result, 1)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].kwargs["timeout"], 600)
        self.assertEqual(run.call_args_list[1].kwargs["timeout"], 600)
        summary = json.loads(output.getvalue().strip().splitlines()[-1])
        self.assertEqual(summary["failed_run_ids"], [401])
        self.assertEqual(summary["processed_run_count"], 1)


if __name__ == "__main__":
    unittest.main()
