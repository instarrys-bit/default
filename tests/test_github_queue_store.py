import gzip
import hashlib
import json
import sys
import tempfile
import unittest
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


class GitHubIssueQueueStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bootstrap = Path(self.temp.name) / "task_queue.json"
        self.document = {"schema_version": 1, "revision": 4, "tasks": []}
        self.bootstrap.write_text(json.dumps(self.document), encoding="utf-8")
        self.comments = []
        self.next_id = 1
        self.calls = []
        self.store = GitHubContentsQueueStore(
            "owner/repo",
            str(self.bootstrap),
            token="test-token",
            api_url="https://api.example.test",
            issue_number=315,
        )

    def tearDown(self):
        self.temp.cleanup()

    def fake_urlopen(self, request, timeout=20):
        self.calls.append(request)
        if request.method == "GET":
            return FakeResponse(self.comments)
        if request.method == "POST":
            body = json.loads(request.data)["body"]
            self.comments.append({"id": self.next_id, "body": body})
            self.next_id += 1
            return FakeResponse({"id": self.next_id - 1})
        raise AssertionError(f"unexpected method: {request.method}")

    def test_read_bootstraps_issue_from_read_only_file(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = self.store.read()
        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(snapshot.content_sha, f"4:{hashlib.sha256(self.store._canonical_bytes(self.document)).hexdigest()}")
        self.assertEqual(len(self.comments), 1)
        self.assertIn("/repos/owner/repo/issues/315/comments", self.calls[0].full_url)
        self.assertEqual(self.calls[0].method, "GET")
        self.assertEqual(self.calls[1].method, "POST")

    def test_compare_and_swap_appends_compressed_snapshot(self):
        candidate = {"schema_version": 1, "revision": 5, "tasks": [{"task_id": "next"}]}
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store.read()
            new_sha = self.store.compare_and_swap(candidate, current.content_sha)
            latest = self.store.read()
        self.assertEqual(latest.document, candidate)
        self.assertEqual(new_sha, latest.content_sha)
        payload = json.loads(self.comments[-1]["body"].split("\n", 1)[1])
        self.assertEqual(payload["encoding"], "gzip+base64")
        self.assertEqual(gzip.decompress(__import__("base64").b64decode(payload["data"])), self.store._canonical_bytes(candidate))
        self.assertEqual(payload["previous_sha256"], hashlib.sha256(self.store._canonical_bytes(self.document)).hexdigest())

    def test_blind_write_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "blind writes"):
            self.store.compare_and_swap(self.document, "")

    def test_compare_and_swap_requires_next_revision(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store.read()
            with self.assertRaisesRegex(ValueError, "advance by exactly one"):
                self.store.compare_and_swap({**self.document, "revision": 8}, current.content_sha)

    def test_mutate_reloads_after_same_revision_race(self):
        race = {"injected": False}

        def concurrent_urlopen(request, timeout=20):
            if request.method == "GET":
                return FakeResponse(self.comments)
            body = json.loads(request.data)["body"]
            if not race["injected"] and '"revision":5' in body:
                race["injected"] = True
                external = {"schema_version": 1, "revision": 5, "tasks": [{"task_id": "other"}]}
                previous = hashlib.sha256(self.store._canonical_bytes(self.document)).hexdigest()
                self.comments.append({"id": self.next_id, "body": self.store._encode_comment(external, previous)})
                self.next_id += 1
            self.comments.append({"id": self.next_id, "body": body})
            self.next_id += 1
            return FakeResponse({"id": self.next_id - 1})

        def add_new(queue):
            queue["revision"] += 1
            queue["tasks"].append({"task_id": "new"})
            return queue, "added"

        with patch("github_queue_store.urlopen", side_effect=concurrent_urlopen):
            result = self.store.mutate(add_new, max_conflicts=2)
            latest = self.store.read()
        self.assertEqual(result, "added")
        self.assertEqual(latest.document["revision"], 6)
        self.assertEqual(latest.document["tasks"], [{"task_id": "other"}, {"task_id": "new"}])

    def test_non_conflict_api_error_does_not_retry(self):
        def forbidden(request, timeout=20):
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with patch("github_queue_store.urlopen", side_effect=forbidden):
            with self.assertRaisesRegex(GitHubAPIError, "HTTP 403"):
                self.store.read()

    def test_malformed_snapshot_fails_closed(self):
        self.comments.append({"id": 1, "body": "<!-- shadowrocket-automation-queue:v1 -->\nnot-json"})
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(GitHubAPIError, "invalid durable queue snapshot"):
                self.store.read()

    def test_mutator_must_return_document(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(ValueError, "queue document object"):
                self.store.mutate(lambda queue: ([], None))

    def test_unchanged_mutation_does_not_append(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(lambda queue: (queue, "unchanged"))
        self.assertEqual(result, "unchanged")
        self.assertEqual(len(self.comments), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
