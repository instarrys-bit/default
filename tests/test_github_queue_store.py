import base64
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
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
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.raw


class GitHubQueueStoreTests(unittest.TestCase):
    def setUp(self):
        self.document = {"schema_version": 1, "revision": 0, "tasks": []}
        self.sha = "blob-v1"
        self.calls = []
        self.store = GitHubContentsQueueStore(
            "owner/repo", token="test-token", api_url="https://api.example.test"
        )

    def fake_urlopen(self, request, timeout=15):
        self.calls.append(request)
        if request.method == "GET":
            encoded = base64.b64encode(json.dumps(self.document).encode()).decode()
            return FakeResponse({"sha": self.sha, "content": encoded})
        payload = json.loads(request.data)
        self.assertEqual(payload["sha"], self.sha)
        self.document = json.loads(base64.b64decode(payload["content"]).decode())
        self.sha = "blob-v2"
        return FakeResponse({"content": {"sha": self.sha}})

    def test_read_returns_document_and_blob_sha(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = self.store.read()
        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(snapshot.content_sha, "blob-v1")
        self.assertIn("/repos/owner/repo/contents/automation/task_queue.json", self.calls[0].full_url)

    def test_compare_and_swap_requires_expected_sha_and_updates(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            new_sha = self.store.compare_and_swap(
                {"schema_version": 1, "revision": 1, "tasks": []}, "blob-v1"
            )
        self.assertEqual(new_sha, "blob-v2")
        self.assertEqual(self.document["revision"], 1)
        payload = json.loads(self.calls[0].data)
        self.assertEqual(payload["sha"], "blob-v1")
        self.assertEqual(payload["branch"], "main")

    def test_blind_write_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "blind writes"):
            self.store.compare_and_swap(self.document, "")

    def test_mutate_reloads_and_reapplies_after_sha_conflict(self):
        sequence = {"gets": 0, "puts": 0}

        def conflict_then_write(request, timeout=15):
            if request.method == "GET":
                sequence["gets"] += 1
                current = {"schema_version": 1, "revision": sequence["gets"] - 1, "tasks": []}
                sha = f"blob-v{sequence['gets']}"
                if sequence["gets"] == 1:
                    self.document = current
                    self.sha = sha
                else:
                    self.document = {"schema_version": 1, "revision": 7, "tasks": [{"task_id": "other"}]}
                    self.sha = "blob-v2"
                    current = self.document
                    sha = self.sha
                encoded = base64.b64encode(json.dumps(current).encode()).decode()
                return FakeResponse({"sha": sha, "content": encoded})
            sequence["puts"] += 1
            if sequence["puts"] == 1:
                raise HTTPError(request.full_url, 409, "Conflict", {}, BytesIO(b"stale sha"))
            body = json.loads(request.data)
            self.assertEqual(body["sha"], "blob-v2")
            saved = json.loads(base64.b64decode(body["content"]).decode())
            self.assertEqual(saved["revision"], 8)
            self.assertEqual(saved["tasks"][0]["task_id"], "other")
            self.assertEqual(saved["tasks"][1]["task_id"], "new")
            return FakeResponse({"content": {"sha": "blob-v3"}})

        def add_task(queue):
            queue["revision"] += 1
            queue["tasks"].append({"task_id": "new"})
            return queue, "added"

        with patch("github_queue_store.urlopen", side_effect=conflict_then_write):
            result = self.store.mutate(add_task, max_conflicts=2)
        self.assertEqual(result, "added")
        self.assertEqual(sequence, {"gets": 2, "puts": 2})

    def test_conflict_budget_exhaustion_fails_closed(self):
        def always_conflict(request, timeout=15):
            if request.method == "GET":
                encoded = base64.b64encode(json.dumps(self.document).encode()).decode()
                return FakeResponse({"sha": self.sha, "content": encoded})
            raise HTTPError(request.full_url, 409, "Conflict", {}, BytesIO(b"stale sha"))

        with patch("github_queue_store.urlopen", side_effect=always_conflict):
            with self.assertRaises(ConcurrentUpdate):
                self.store.mutate(
                    lambda q: ({**q, "revision": q["revision"] + 1}, None),
                    max_conflicts=1,
                )

    def test_non_conflict_api_error_does_not_retry(self):
        def forbidden(request, timeout=15):
            raise HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO(b"denied"))

        with patch("github_queue_store.urlopen", side_effect=forbidden):
            with self.assertRaisesRegex(GitHubAPIError, "HTTP 403"):
                self.store.read()

    def test_mutator_must_return_document(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(ValueError, "queue document object"):
                self.store.mutate(lambda q: ([], None))

    def test_unchanged_mutation_does_not_commit(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(lambda q: (q, "unchanged"))
        self.assertEqual(result, "unchanged")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
