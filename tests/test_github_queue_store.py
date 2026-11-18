import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
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

    def test_rebuilt_queue_uses_clean_seed_instead_of_stale_revision_250(self):
        stale = Path(self.temp.name) / "stale-task-queue.json"
        stale.write_text(json.dumps({"schema_version": 1, "revision": 250, "tasks": []}), encoding="utf-8")
        seed = Path(self.temp.name) / "clean-seed.json"
        clean = {
            "schema_version": 1,
            "revision": 0,
            "tasks": [],
            "resource_leases": {},
            "manual_authorizations": {},
        }
        seed.write_text(json.dumps(clean), encoding="utf-8")
        rebuilt = GitHubContentsQueueStore(
            "owner/repo",
            str(stale),
            token="test-token",
            api_url="https://api.example.test",
            issue_number=423,
            bootstrap_path=str(seed),
        )
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = rebuilt.read()
        self.assertEqual(snapshot.document, clean)
        self.assertEqual(snapshot.content_sha, "")
        self.assertEqual(len(self.comments), 0)

    def test_queue_history_reads_continue_past_one_hundred_pages_concurrently(self):
        import threading
        requested_pages = []
        first_batch_barrier = threading.Barrier(4)

        def paginated_urlopen(request, timeout=20):
            from urllib.parse import parse_qs, urlparse
            page = int(parse_qs(urlparse(request.full_url).query)["page"][0])
            requested_pages.append(page)
            if page in {2, 3, 4, 5}:
                first_batch_barrier.wait(timeout=3)
            count = 100 if page <= 101 else 7
            return FakeResponse([{"id": page * 100 + index, "body": "ordinary comment"} for index in range(count)])

        with patch("github_queue_store.urlopen", side_effect=paginated_urlopen):
            comments = self.store._all_comments()

        self.assertEqual(len(comments), 10107)
        self.assertTrue(set(range(1, 103)).issubset(set(requested_pages)))
        self.assertEqual(len(requested_pages), len(set(requested_pages)))
        self.assertLessEqual(max(requested_pages), 105)

    def test_read_only_consumer_does_not_bootstrap_or_write(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = self.store.read()
        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(snapshot.content_sha, "")
        self.assertEqual(len(self.comments), 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0].method, "GET")

    def test_compare_and_swap_appends_compressed_snapshot(self):
        candidate = {"schema_version": 1, "revision": 5, "tasks": [{"task_id": "next"}]}
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store._ensure_bootstrap()
            new_sha = self.store.compare_and_swap(candidate, current.content_sha)
            latest = self.store.read()
        self.assertEqual(latest.document, candidate)
        self.assertEqual(new_sha, latest.content_sha)
        payload = json.loads(self.comments[-1]["body"].split("\n", 1)[1])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["encoding"], "gzip+base64")
        self.assertEqual(gzip.decompress(__import__("base64").b64decode(payload["data"])), self.store._canonical_bytes(candidate))
        self.assertEqual(payload["previous_sha256"], hashlib.sha256(self.store._canonical_bytes(self.document)).hexdigest())

    def test_large_snapshot_is_chunked_and_round_trips(self):
        blob = "".join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(5000))
        candidate = {"schema_version": 1, "revision": 5, "tasks": [{"task_id": "large", "evidence": blob}]}
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store._ensure_bootstrap()
            self.store.compare_and_swap(candidate, current.content_sha)
            latest = self.store.read()
        self.assertEqual(latest.document, candidate)
        self.assertGreater(len(self.comments), 3)
        self.assertTrue(all(len(item["body"].encode("utf-8")) < 60_000 for item in self.comments))
        self.assertEqual(latest.content_sha, f"5:{hashlib.sha256(self.store._canonical_bytes(candidate)).hexdigest()}")

    def test_incomplete_chunk_upload_is_ignored(self):
        raw = self.store._canonical_bytes({"schema_version": 1, "revision": 5, "tasks": []})
        compressed = __import__("gzip").compress(raw, mtime=0)
        encoded = __import__("base64").b64encode(compressed).decode("ascii")
        payload = {
            "schema_version": 2, "kind": "part", "revision": 5,
            "previous_sha256": hashlib.sha256(self.store._canonical_bytes(self.document)).hexdigest(),
            "sha256": hashlib.sha256(raw).hexdigest(), "encoding": "gzip+base64",
            "index": 0, "total": 2, "data": encoded,
        }
        self.comments.append({"id": 1, "body": "<!-- shadowrocket-automation-queue:v2 -->\n" + json.dumps(payload)})
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            snapshot = self.store.read()
        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(snapshot.content_sha, "")

    def test_blind_write_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "blind writes"):
            self.store.compare_and_swap(self.document, "")

    def test_compare_and_swap_requires_next_revision(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store._ensure_bootstrap()
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
            raise HTTPError(
                request.full_url, 403, "Forbidden",
                {"X-GitHub-Request-Id": "ABC123", "X-RateLimit-Remaining": "42"},
                BytesIO(b'{"message":"Resource not accessible by integration"}'),
            )

        with patch("github_queue_store.urlopen", side_effect=forbidden) as mocked:
            with self.assertRaisesRegex(
                GitHubAPIError,
                r"GET /repos/owner/repo/issues/315/comments; HTTP 403; "
                r"message=Resource not accessible by integration; request_id=ABC123; "
                r"rate_limit_remaining=42",
            ):
                self.store.read()
        self.assertEqual(mocked.call_count, 1)

    def test_transient_get_network_failure_retries_with_bounded_backoff(self):
        attempts = {"count": 0}

        def flaky_get(request, timeout=20):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise URLError("temporary network interruption")
            return self.fake_urlopen(request, timeout)

        with patch("github_queue_store.urlopen", side_effect=flaky_get), patch("github_queue_store.time.sleep") as sleep:
            snapshot = self.store.read()

        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(attempts["count"], 2)
        sleep.assert_called_once()

    def test_secondary_rate_limit_on_get_retries_with_retry_after(self):
        attempts = {"count": 0}

        def rate_limited_get(request, timeout=20):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise HTTPError(
                    request.full_url, 403, "secondary rate limit",
                    {"Retry-After": "0"}, BytesIO(b'{"message":"You have exceeded a secondary rate limit."}'),
                )
            return self.fake_urlopen(request, timeout)

        with patch("github_queue_store.urlopen", side_effect=rate_limited_get), patch("github_queue_store.time.sleep") as sleep:
            snapshot = self.store.read()

        self.assertEqual(snapshot.document, self.document)
        self.assertEqual(attempts["count"], 2)
        sleep.assert_called_once_with(0.0)

    def test_permission_403_is_not_retried(self):
        attempts = {"count": 0}

        def forbidden_get(request, timeout=20):
            attempts["count"] += 1
            raise HTTPError(
                request.full_url, 403, "forbidden",
                {"X-RateLimit-Remaining": "4999"},
                BytesIO(b'{"message":"Resource not accessible by integration"}'),
            )

        with patch("github_queue_store.urlopen", side_effect=forbidden_get), patch("github_queue_store.time.sleep") as sleep:
            with self.assertRaisesRegex(GitHubAPIError, "HTTP 403"):
                self.store.read()

        self.assertEqual(attempts["count"], 1)
        sleep.assert_not_called()

    def test_ambiguous_post_failure_is_not_retried(self):
        attempts = {"count": 0}

        def failed_post(request, timeout=20):
            attempts["count"] += 1
            raise URLError("connection lost after request submission")

        with patch("github_queue_store.urlopen", side_effect=failed_post), patch("github_queue_store.time.sleep") as sleep:
            with self.assertRaisesRegex(GitHubAPIError, "failed or timed out"):
                self.store._post_comment("snapshot")

        self.assertEqual(attempts["count"], 1)
        sleep.assert_not_called()

    def test_malformed_snapshot_fails_closed(self):
        self.comments.append({"id": 1, "body": "<!-- shadowrocket-automation-queue:v1 -->\nnot-json"})
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(GitHubAPIError, "invalid durable queue snapshot"):
                self.store.read()

    def test_mutator_must_return_document(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(ValueError, "queue document object"):
                self.store.mutate(lambda queue: ([], None))

    def test_mutate_reuses_its_snapshot_instead_of_rescanning_before_append(self):
        def add_task(queue):
            queue["revision"] += 1
            queue["tasks"].append({"task_id": "new"})
            return queue, "added"

        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(add_task)
        self.assertEqual(result, "added")
        get_calls = [request for request in self.calls if request.method == "GET"]
        # Initial read, post-bootstrap verification, and post-append canonical
        # verification. A fourth full-history GET would be redundant.
        self.assertEqual(len(get_calls), 3)

    def test_unchanged_mutation_does_not_append(self):
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(lambda queue: (queue, "unchanged"))
        self.assertEqual(result, "unchanged")
        self.assertEqual(len(self.comments), 1)  # compact bootstrap snapshot stays in one comment


    def test_mutations_write_only_issue_comments_not_repository_contents(self):
        candidate = {"schema_version": 1, "revision": 5, "tasks": [{"task_id": "next"}]}
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            current = self.store._ensure_bootstrap()
            self.store.compare_and_swap(candidate, current.content_sha)

        self.assertTrue(
            any(call.method == "POST" and "/issues/315/comments" in call.full_url for call in self.calls)
        )
        self.assertTrue(all("/issues/315/comments" in call.full_url for call in self.calls))
        self.assertFalse(any(call.method == "PUT" or "/contents/" in call.full_url for call in self.calls))



class GitHubQueueEpochRotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bootstrap = Path(self.temp.name) / "task_queue.json"
        self.document = {
            "schema_version": 1,
            "revision": 877,
            "tasks": [{"task_id": "task-preserve-this", "status": "QUEUED"}],
            "resource_leases": {},
            "manual_authorizations": {},
        }
        self.bootstrap.write_text(json.dumps(self.document), encoding="utf-8")
        self.issue_comments = {423: [], 571: []}
        self.next_comment_id = 10000
        self.next_issue_number = 609
        self.created_issues = []
        self.calls = []
        self.store = GitHubContentsQueueStore(
            "owner/repo",
            str(self.bootstrap),
            token="test-token",
            api_url="https://api.example.test",
            index_issue_number=571,
            rotate_comment_threshold=2400,
        )
        snapshot_digest = self.store._digest(self.document)
        pointer = {
            "schema_version": 1,
            "epoch": 1,
            "issue_number": 423,
            "previous_sha256": None,
            "source_artifact_digest": "sha256:" + "a" * 64,
            "source_artifact_run_id": 43826128047,
            "source_issue_number": 423,
            "source_revision": 877,
            "source_snapshot_sha256": snapshot_digest,
        }
        pointer["sha256"] = hashlib.sha256(
            self.store._canonical_bytes(pointer)
        ).hexdigest()
        self.issue_comments[571] = [{
            "id": 1,
            "body": "<!-- shadowrocket-automation-queue-index:v1 -->\n"
                    + json.dumps(pointer, sort_keys=True, separators=(",", ":")),
        }]
        snapshot_body = self.store._encode_comment(self.document, None)
        self.issue_comments[423] = [
            {"id": index, "body": "ordinary historical comment"}
            for index in range(2, 2501)
        ] + [{"id": 2501, "body": snapshot_body}]

    def tearDown(self):
        self.temp.cleanup()

    def fake_urlopen(self, request, timeout=20):
        from urllib.parse import parse_qs, urlparse
        self.calls.append(request)
        parsed = urlparse(request.full_url)
        path = parsed.path
        if request.method == "GET" and path.endswith("/search/issues"):
            return FakeResponse({"items": [
                issue for issue in self.created_issues
                if issue["title"] in parse_qs(parsed.query).get("q", [""])[0]
            ]})
        if request.method == "GET" and path.endswith("/comments"):
            issue_number = int(path.split("/")[-2])
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            comments = self.issue_comments.get(issue_number, [])
            return FakeResponse(comments[(page - 1) * 100:page * 100])
        if request.method == "POST" and path.endswith("/issues"):
            payload = json.loads(request.data)
            issue = {
                "number": self.next_issue_number,
                "title": payload["title"],
                "body": payload["body"],
            }
            self.created_issues.append(issue)
            self.issue_comments[self.next_issue_number] = []
            self.next_issue_number += 1
            return FakeResponse(issue)
        if request.method == "POST" and path.endswith("/comments"):
            issue_number = int(path.split("/")[-2])
            payload = json.loads(request.data)
            comment = {"id": self.next_comment_id, "body": payload["body"]}
            self.next_comment_id += 1
            self.issue_comments.setdefault(issue_number, []).append(comment)
            return FakeResponse({"id": comment["id"]})
        raise AssertionError(f"unexpected request: {request.method} {request.full_url}")

    def test_epoch_rotation_checkpoints_exact_queue_before_switching_index(self):
        original_tasks = json.loads(json.dumps(self.document["tasks"]))

        def add_one_task(queue):
            queue["revision"] += 1
            queue["tasks"].append({"task_id": "task-after-rotation", "status": "QUEUED"})
            return queue, "appended"

        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(add_one_task)
            latest = self.store.read()

        self.assertEqual(result, "appended")
        self.assertEqual(latest.document["revision"], 878)
        self.assertEqual(
            latest.document["tasks"],
            original_tasks + [{"task_id": "task-after-rotation", "status": "QUEUED"}],
        )
        self.assertEqual(len(self.issue_comments[423]), 2500)
        self.assertEqual(len(self.created_issues), 1)
        self.assertEqual(len(self.issue_comments[609]), 2)
        pointer = self.store._canonical_index_pointer(self.issue_comments[571])
        self.assertEqual(pointer["epoch"], 2)
        self.assertEqual(pointer["issue_number"], 609)
        self.assertEqual(pointer["revision"], 877)
        self.assertEqual(pointer["snapshot_sha256"], self.store._digest(self.document))
        self.assertTrue(self.store._snapshot_matches_pointer(self.issue_comments[609], pointer))
        self.assertEqual(
            self.store._canonical_snapshot(self.issue_comments[609]).document["tasks"],
            original_tasks + [{"task_id": "task-after-rotation", "status": "QUEUED"}],
        )
        self.assertTrue(all("/contents/" not in request.full_url for request in self.calls))
        self.assertTrue(any(
            request.method == "POST" and "/issues/571/comments" in request.full_url
            for request in self.calls
        ))
        self.assertTrue(any(
            request.method == "POST" and "/issues/609/comments" in request.full_url
            for request in self.calls
        ))

    def test_index_pointer_digest_mismatch_fails_closed(self):
        pointer_comment = self.issue_comments[571][0]
        payload = json.loads(pointer_comment["body"].split("\n", 1)[1])
        payload["issue_number"] = 609
        pointer_comment["body"] = (
            "<!-- shadowrocket-automation-queue-index:v1 -->\n"
            + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            with self.assertRaisesRegex(GitHubAPIError, "pointer digest mismatch"):
                self.store.read()

    def test_existing_epoch_issue_is_reused_after_interrupted_rotation(self):
        digest = self.store._digest(self.document)
        marker = f"<!-- shadowrocket-automation-queue-epoch:v1 key=2:877:{digest} -->"
        self.created_issues.append({
            "number": 609,
            "title": f"Durable automation queue epoch 2 revision 877 {digest[:12]}",
            "body": marker,
        })
        self.issue_comments[609] = [{
            "id": 2502,
            "body": self.store._encode_comment(self.document, None),
        }]
        self.next_issue_number = 610

        def append_after_interrupted_rotation(queue):
            queue["revision"] += 1
            queue["tasks"].append({
                "task_id": "task-after-interrupted-rotation",
                "status": "QUEUED",
            })
            return queue, "resumed"

        with patch("github_queue_store.urlopen", side_effect=self.fake_urlopen):
            result = self.store.mutate(append_after_interrupted_rotation)
            latest = self.store.read()

        self.assertEqual(result, "resumed")
        self.assertEqual(len(self.created_issues), 1)
        pointer = self.store._canonical_index_pointer(self.issue_comments[571])
        self.assertEqual(pointer["epoch"], 2)
        self.assertEqual(pointer["issue_number"], 609)
        self.assertEqual(len(self.issue_comments[609]), 2)
        self.assertEqual(latest.document["revision"], 878)
        self.assertEqual(
            latest.document["tasks"],
            self.document["tasks"] + [{
                "task_id": "task-after-interrupted-rotation",
                "status": "QUEUED",
            }],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
