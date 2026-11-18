from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from github_queue_store import (
    ConcurrentUpdate,
    GitHubAPIError,
    GitHubContentsQueueStore,
)


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.raw


class RepositoryJsonQueueStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.seed_path = Path(self.temp.name) / "task_queue.json"
        self.document = {
            "schema_version": 1,
            "revision": 4,
            "tasks": [{"task_id": "existing", "status": "QUEUED"}],
            "resource_leases": {},
        }
        self.remote = {"document": self.document, "sha": "blob-v1"}
        self.calls = []
        self.put_payloads = []
        self.store = GitHubContentsQueueStore(
            "owner/repo",
            token="test-token",
            api_url="https://api.example.test",
        )

    def tearDown(self):
        self.temp.cleanup()

    def fake_urlopen(self, request, timeout=20):
        self.calls.append(request)
        if request.method == "GET":
            if self.remote is None:
                raise HTTPError(
                    request.full_url, 404, "Not Found", {},
                    BytesIO(b'{"message":"Not Found"}'),
                )
            raw = json.dumps(
                self.remote["document"], ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8")
            return FakeResponse({
                "content": base64.b64encode(raw).decode("ascii"),
                "sha": self.remote["sha"],
            })
        if request.method == "PUT":
            payload = json.loads(request.data.decode("utf-8"))
            self.put_payloads.append(payload)
            raw = base64.b64decode(payload["content"]).decode("utf-8")
            document = json.loads(raw)
            next_sha = f"blob-v{len(self.put_payloads) + 1}"
            self.remote = {"document": document, "sha": next_sha}
            return FakeResponse({"content": {"sha": next_sha}})
        raise AssertionError(f"unexpected method: {request.method}")

    def test_read_uses_contents_api_and_verifies_blob_sha(self):
        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = self.store.read()

        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(snapshot.git_blob_sha, "blob-v1")
        self.assertTrue(snapshot.content_sha.startswith("4:"))
        self.assertIn("/repos/owner/repo/contents/automation/task_queue.json?ref=main", self.calls[0].full_url)
        self.assertEqual(self.calls[0].get_header("Authorization"), "Bearer test-token")
        self.assertFalse(any("/issues/" in request.full_url for request in self.calls))

    def test_missing_remote_uses_local_seed_without_writing(self):
        self.remote = None
        seed = {
            "schema_version": 1,
            "revision": 0,
            "tasks": [],
            "resource_leases": {},
        }
        self.seed_path.write_text(json.dumps(seed), encoding="utf-8")
        store = GitHubContentsQueueStore(
            "owner/repo",
            token="test-token",
            api_url="https://api.example.test",
            bootstrap_path=str(self.seed_path),
        )

        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = store.read()

        self.assertEqual(snapshot.document, seed)
        self.assertEqual(snapshot.content_sha, "")
        self.assertEqual(len(self.put_payloads), 0)

    def test_bootstrap_persists_seed_with_contents_api(self):
        self.remote = None
        seed = {
            "schema_version": 1,
            "revision": 0,
            "tasks": [],
            "resource_leases": {},
        }
        self.seed_path.write_text(json.dumps(seed), encoding="utf-8")
        store = GitHubContentsQueueStore(
            "owner/repo",
            token="test-token",
            api_url="https://api.example.test",
            bootstrap_path=str(self.seed_path),
        )

        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = store._ensure_bootstrap()

        self.assertEqual(snapshot.document, seed)
        self.assertEqual(snapshot.git_blob_sha, "blob-v2")
        self.assertEqual(len(self.put_payloads), 1)
        self.assertNotIn("sha", self.put_payloads[0])
        self.assertEqual(self.put_payloads[0]["branch"], "main")

    def test_compare_and_swap_uses_current_git_blob_sha(self):
        candidate = {**self.document, "revision": 5, "tasks": self.document["tasks"] + [{"task_id": "next"}]}

        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store.read()
            result = self.store.compare_and_swap(candidate, current.content_sha)
            latest = self.store.read()

        self.assertEqual(result, latest.content_sha)
        self.assertEqual(latest.document, candidate)
        self.assertEqual(self.put_payloads[0]["sha"], "blob-v1")
        self.assertEqual(self.put_payloads[0]["branch"], "main")

    def test_compare_and_swap_rejects_stale_logical_sha(self):
        candidate = {**self.document, "revision": 5}
        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(ConcurrentUpdate, "sha mismatch"):
                self.store.compare_and_swap(candidate, "stale")
        self.assertEqual(len(self.put_payloads), 0)

    def test_compare_and_swap_requires_exactly_next_revision(self):
        candidate = {**self.document, "revision": 6}
        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store.read()
            with self.assertRaisesRegex(ValueError, "revision must advance by one"):
                self.store.compare_and_swap(candidate, current.content_sha)
        self.assertEqual(len(self.put_payloads), 0)

    def test_unchanged_mutation_does_not_write(self):
        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(lambda queue: (queue, "unchanged"))

        self.assertEqual(result, "unchanged")
        self.assertEqual(len(self.put_payloads), 0)

    def test_mutation_writes_one_revision_and_verifies_remote_content(self):
        def add_task(queue):
            queue["revision"] += 1
            queue["tasks"].append({"task_id": "new", "status": "QUEUED"})
            return queue, "added"

        with patch("storage.v2.queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(add_task)
            latest = self.store.read()

        self.assertEqual(result, "added")
        self.assertEqual(latest.document["revision"], 5)
        self.assertEqual(latest.document["tasks"][-1]["task_id"], "new")
        self.assertEqual(len(self.put_payloads), 1)

    def test_http_409_is_reported_as_concurrent_update(self):
        def conflict(request, timeout=20):
            raise HTTPError(request.full_url, 409, "Conflict", {}, BytesIO(b"{}"))

        with patch("storage.v2.queue_store.urlopen", side_effect=conflict):
            with self.assertRaises(ConcurrentUpdate):
                self.store._request("PUT", self.store.contents_endpoint, {})

    def test_permission_403_fails_closed_without_retry(self):
        attempts = {"count": 0}

        def forbidden(request, timeout=20):
            attempts["count"] += 1
            raise HTTPError(
                request.full_url, 403, "Forbidden", {},
                BytesIO(b'{"message":"Resource not accessible by integration"}'),
            )

        with patch("storage.v2.queue_store.urlopen", side_effect=forbidden):
            with self.assertRaisesRegex(GitHubAPIError, "GET HTTP 403"):
                self.store.read()

        self.assertEqual(attempts["count"], 1)

    def test_network_failure_fails_closed(self):
        def unavailable(request, timeout=20):
            raise URLError("temporary network interruption")

        with patch("storage.v2.queue_store.urlopen", side_effect=unavailable):
            with self.assertRaisesRegex(GitHubAPIError, "temporary network interruption"):
                self.store.read()

    def test_store_has_no_issue_transport_or_issue_number_switch(self):
        self.assertFalse(hasattr(self.store, "issue_number"))
        self.assertNotIn("/issues/", self.store.contents_endpoint)

    def test_storage_store_rejects_non_allowlisted_repository_paths(self):
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            GitHubContentsQueueStore("owner/repo", "modules/uu.conf", token="test-token")
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            GitHubContentsQueueStore("owner/repo", "rulesets/direct.list", token="test-token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
