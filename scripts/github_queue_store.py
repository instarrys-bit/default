#!/usr/bin/env python3
"""Append-only GitHub Issue comment snapshots for durable automation queue state.

The repository bootstrap JSON is read-only. All queue mutations are appended as
compressed, integrity-checked Issue comments; no repository contents are written.
"""
from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MARKER = "<!-- shadowrocket-automation-queue:v1 -->"
MARKER_V2 = "<!-- shadowrocket-automation-queue:v2 -->"
DEFAULT_ISSUE_NUMBER = 423
MAX_COMMENT_BYTES = 60_000
CHUNK_DATA_CHARS = 40_000


class QueueStoreError(RuntimeError):
    """Base error for durable queue storage."""


class ConcurrentUpdate(QueueStoreError):
    """A newer canonical queue revision won the append-only race."""


class GitHubAPIError(QueueStoreError):
    """GitHub rejected or could not complete a queue storage request."""


@dataclass(frozen=True)
class QueueSnapshot:
    document: dict[str, Any]
    content_sha: str


class GitHubContentsQueueStore:
    """Compatibility-named queue adapter backed by append-only Issue comments.

    Each successful mutation appends revision N+1 with the digest of revision N.
    If concurrent writers append the same revision, the earliest matching
    comment ID is canonical and later duplicates are ignored. Mutators are
    retried against the canonical latest snapshot after losing that race.
    """

    def __init__(
        self,
        repository: str,
        path: str = "automation/task_queue.json",
        *,
        branch: str = "main",
        token: str | None = None,
        api_url: str = "https://api.github.com",
        timeout: int = 20,
        issue_number: int | None = None,
        bootstrap_path: str | None = None,
    ) -> None:
        if not repository or "/" not in repository:
            raise ValueError("repository must be owner/name")
        if not path or ".." in path.split("/") or (not Path(path).is_absolute() and path.startswith("/")):
            raise ValueError("path must be a safe repository-relative path")
        if not branch:
            raise ValueError("branch is required")
        self.repository = repository
        self.path = path
        self.branch = branch
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        raw_issue = issue_number if issue_number is not None else os.environ.get(
            "AUTOMATION_QUEUE_ISSUE_NUMBER", str(DEFAULT_ISSUE_NUMBER)
        )
        try:
            self.issue_number = int(raw_issue)
        except (TypeError, ValueError):
            raise ValueError("AUTOMATION_QUEUE_ISSUE_NUMBER must be a positive integer") from None
        if self.issue_number < 1:
            raise ValueError("AUTOMATION_QUEUE_ISSUE_NUMBER must be a positive integer")
        self.bootstrap_path = bootstrap_path or os.environ.get("AUTOMATION_QUEUE_BOOTSTRAP_PATH") or (
            "automation/task_queue_rebuild_seed.json"
            if self.issue_number == DEFAULT_ISSUE_NUMBER else path
        )
        if (not self.bootstrap_path or ".." in self.bootstrap_path.split("/")
                or self.bootstrap_path.startswith("/")):
            raise ValueError("bootstrap_path must be a safe repository-relative path")

    @property
    def comments_endpoint(self) -> str:
        return f"{self.api_url}/repos/{self.repository}/issues/{self.issue_number}/comments"

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.token:
            raise GitHubAPIError("GitHub token is required; token value was not logged")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shadowrocket-automation-issue-queue",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace").lower()
            if exc.code == 409:
                raise ConcurrentUpdate("queue snapshot append conflicted; re-read before retrying") from None
            raise GitHubAPIError(f"GitHub Issues API returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise GitHubAPIError("GitHub Issues API request failed or timed out") from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubAPIError("GitHub Issues API returned invalid JSON") from None

    @staticmethod
    def _canonical_bytes(document: dict[str, Any]) -> bytes:
        return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _digest(cls, document: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical_bytes(document)).hexdigest()

    def _encode_comment(self, document: dict[str, Any], previous_sha256: str | None) -> str:
        raw = self._canonical_bytes(document)
        compressed = gzip.compress(raw, mtime=0)
        payload = {
            "schema_version": 1,
            "revision": document.get("revision"),
            "previous_sha256": previous_sha256,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "encoding": "gzip+base64",
            "data": base64.b64encode(compressed).decode("ascii"),
        }
        body = MARKER + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
            raise GitHubAPIError("compressed queue snapshot exceeds the safe GitHub comment size")
        return body

    @staticmethod
    def _decode_comment(comment: dict[str, Any]) -> tuple[int, str | None, str, dict[str, Any]] | None:
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(MARKER + "\n"):
            return None
        try:
            payload = json.loads(body.split("\n", 1)[1])
            if payload.get("schema_version") != 1 or payload.get("encoding") != "gzip+base64":
                raise ValueError("unsupported queue snapshot format")
            compressed = base64.b64decode(payload["data"], validate=True)
            raw = gzip.decompress(compressed)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != payload.get("sha256"):
                raise ValueError("queue snapshot digest mismatch")
            document = json.loads(raw.decode("utf-8"))
            revision = payload.get("revision")
            if (not isinstance(document, dict) or isinstance(revision, bool)
                    or not isinstance(revision, int) or document.get("revision") != revision):
                raise ValueError("queue snapshot revision mismatch")
            comment_id = comment.get("id")
            if isinstance(comment_id, bool) or not isinstance(comment_id, int):
                raise ValueError("queue snapshot comment is missing its numeric ID")
            previous = payload.get("previous_sha256")
            if previous is not None and (not isinstance(previous, str) or len(previous) != 64):
                raise ValueError("queue snapshot previous digest is invalid")
            return revision, previous, digest, document
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            raise GitHubAPIError(f"invalid durable queue snapshot comment: {exc}") from None

    def _all_comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urlencode({"per_page": 100, "page": page})
            result = self._request("GET", f"{self.comments_endpoint}?{query}")
            if not isinstance(result, list):
                raise GitHubAPIError("GitHub Issue comments response must be an array")
            comments.extend(item for item in result if isinstance(item, dict))
            if len(result) < 100:
                break
            page += 1
            if page > 100:
                raise GitHubAPIError("durable queue comment history exceeds the pagination safety limit")
        return comments

    def _post_comment(self, body: str) -> int:
        if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
            raise GitHubAPIError("queue snapshot chunk exceeds the safe GitHub comment size")
        result = self._request("POST", self.comments_endpoint, {"body": body})
        comment_id = result.get("id") if isinstance(result, dict) else None
        if isinstance(comment_id, bool) or not isinstance(comment_id, int):
            raise GitHubAPIError("GitHub Issue comment response is missing its numeric ID")
        return comment_id

    def _append(self, document: dict[str, Any], previous_sha256: str | None) -> int:
        raw = self._canonical_bytes(document)
        compressed = gzip.compress(raw, mtime=0)
        encoded = base64.b64encode(compressed).decode("ascii")
        digest = hashlib.sha256(raw).hexdigest()
        revision = document.get("revision")
        # Preserve the compact one-comment v1 representation for ordinary
        # snapshots; use chunking only when the complete payload exceeds the
        # safe comment size. This prevents unnecessary growth of Issue history.
        legacy_payload = {
            "schema_version": 1, "revision": revision,
            "previous_sha256": previous_sha256, "sha256": digest,
            "encoding": "gzip+base64", "data": encoded,
        }
        legacy_body = MARKER + "\n" + json.dumps(legacy_payload, sort_keys=True, separators=(",", ":"))
        if len(legacy_body.encode("utf-8")) <= MAX_COMMENT_BYTES:
            return self._post_comment(legacy_body)
        total = max(1, (len(encoded) + CHUNK_DATA_CHARS - 1) // CHUNK_DATA_CHARS)
        # Parts are immutable and independently addressable. The final commit
        # comment is the only record readers accept, so interrupted uploads are
        # ignored and concurrent writers cannot mix their chunks.
        for index in range(total):
            part = encoded[index * CHUNK_DATA_CHARS:(index + 1) * CHUNK_DATA_CHARS]
            payload = {
                "schema_version": 2, "kind": "part", "revision": revision,
                "previous_sha256": previous_sha256, "sha256": digest,
                "encoding": "gzip+base64", "index": index, "total": total,
                "data": part,
            }
            self._post_comment(MARKER_V2 + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":")))
        commit = {
            "schema_version": 2, "kind": "commit", "revision": revision,
            "previous_sha256": previous_sha256, "sha256": digest,
            "encoding": "gzip+base64", "total": total,
        }
        return self._post_comment(MARKER_V2 + "\n" + json.dumps(commit, sort_keys=True, separators=(",", ":")))

    def _decode_v2_commit(self, comment: dict[str, Any], comments: list[dict[str, Any]]) -> tuple[int, str | None, str, dict[str, Any]] | None:
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(MARKER_V2 + "\n"):
            return None
        try:
            payload = json.loads(body.split("\n", 1)[1])
            if payload.get("schema_version") != 2 or payload.get("kind") != "commit" or payload.get("encoding") != "gzip+base64":
                return None
            revision, digest, total = payload.get("revision"), payload.get("sha256"), payload.get("total")
            previous = payload.get("previous_sha256")
            if (isinstance(revision, bool) or not isinstance(revision, int)
                    or not isinstance(total, int) or isinstance(total, bool) or total < 1
                    or not isinstance(digest, str) or len(digest) != 64
                    or (previous is not None and (not isinstance(previous, str) or len(previous) != 64))):
                raise ValueError("invalid chunked queue commit metadata")
            parts: dict[int, str] = {}
            for item in comments:
                part_body = item.get("body")
                if not isinstance(part_body, str) or not part_body.startswith(MARKER_V2 + "\n"):
                    continue
                part = json.loads(part_body.split("\n", 1)[1])
                if (part.get("schema_version") == 2 and part.get("kind") == "part"
                        and part.get("revision") == revision and part.get("sha256") == digest
                        and part.get("previous_sha256") == previous and part.get("total") == total):
                    index, data = part.get("index"), part.get("data")
                    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < total and isinstance(data, str):
                        parts.setdefault(index, data)
            if len(parts) != total:
                return None
            encoded = "".join(parts[index] for index in range(total))
            compressed = base64.b64decode(encoded, validate=True)
            raw = gzip.decompress(compressed)
            actual_digest = hashlib.sha256(raw).hexdigest()
            if actual_digest != digest:
                raise ValueError("chunked queue snapshot digest mismatch")
            document = json.loads(raw.decode("utf-8"))
            if not isinstance(document, dict) or document.get("revision") != revision:
                raise ValueError("chunked queue snapshot revision mismatch")
            comment_id = comment.get("id")
            if isinstance(comment_id, bool) or not isinstance(comment_id, int):
                raise ValueError("chunked queue commit is missing its numeric ID")
            return revision, previous, digest, document
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            raise GitHubAPIError(f"invalid durable queue snapshot commit: {exc}") from None

    def _canonical_snapshot(self, comments: list[dict[str, Any]]) -> QueueSnapshot | None:
        candidates: list[tuple[int, int, str | None, str, dict[str, Any]]] = []
        for comment in comments:
            decoded = self._decode_comment(comment)
            if decoded is None:
                decoded = self._decode_v2_commit(comment, comments)
            if decoded is None:
                continue
            revision, previous, digest, document = decoded
            candidates.append((revision, int(comment["id"]), previous, digest, document))
        if not candidates:
            return None
        by_revision: dict[int, list[tuple[int, str | None, str, dict[str, Any]]]] = {}
        for revision, comment_id, previous, digest, document in candidates:
            by_revision.setdefault(revision, []).append((comment_id, previous, digest, document))
        initial_revisions = sorted(
            revision for revision, items in by_revision.items()
            if any(previous is None for _, previous, _, _ in items)
        )
        if not initial_revisions:
            raise GitHubAPIError("durable queue history has no bootstrap snapshot")
        revision = initial_revisions[0]
        initial = sorted(
            (item for item in by_revision[revision] if item[1] is None),
            key=lambda item: item[0],
        )[0]
        comment_id, _, digest, document = initial
        current = QueueSnapshot(document=document, content_sha=f"{revision}:{digest}")
        while revision + 1 in by_revision:
            next_items = sorted(by_revision[revision + 1], key=lambda item: item[0])
            matching = next((item for item in next_items if item[1] == digest), None)
            if matching is None:
                break
            comment_id, _, digest, document = matching
            revision += 1
            current = QueueSnapshot(document=document, content_sha=f"{revision}:{digest}")
        return current

    def read(self) -> QueueSnapshot:
        comments = self._all_comments()
        snapshot = self._canonical_snapshot(comments)
        if snapshot is not None:
            return snapshot
        bootstrap_file = Path(self.bootstrap_path)
        try:
            document = json.loads(bootstrap_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise GitHubAPIError("no durable queue snapshot exists and the read-only bootstrap queue is unavailable") from None
        if not isinstance(document, dict) or isinstance(document.get("revision"), bool) or not isinstance(document.get("revision"), int):
            raise GitHubAPIError("read-only bootstrap queue has an invalid envelope")
        # Read-only consumers can inspect the seed without needing Issues write access.
        return QueueSnapshot(document=document, content_sha="")

    def _ensure_bootstrap(self) -> QueueSnapshot:
        snapshot = self.read()
        if snapshot.content_sha:
            return snapshot
        self._append(snapshot.document, None)
        snapshot = self.read()
        if not snapshot.content_sha:
            raise GitHubAPIError("queue bootstrap comment was not visible after creation")
        return snapshot

    def _compare_and_swap_from_snapshot(
        self, document: dict[str, Any], expected_sha: str, current: QueueSnapshot
    ) -> str:
        """Append against a previously read snapshot, then verify the canonical winner.

        The final read is the concurrency check: if another writer appended the
        same next revision first, or advanced the chain while this writer was
        preparing its candidate, the candidate cannot become the canonical
        snapshot and the mutation is retried. Reusing the caller's just-read
        snapshot avoids a redundant full-history scan before the append.
        """
        if not isinstance(document, dict):
            raise ValueError("queue document must be an object")
        if not expected_sha:
            raise ValueError("expected_sha is required; blind writes are prohibited")
        if not current.content_sha:
            raise ConcurrentUpdate("queue snapshot chain is not initialized; use mutate() to bootstrap")
        if current.content_sha != expected_sha:
            raise ConcurrentUpdate("queue revision changed; re-read before retrying")
        expected_revision = current.document["revision"] + 1
        if document.get("revision") != expected_revision:
            raise ValueError("queue revision must advance by exactly one")
        previous_digest = self._digest(current.document)
        self._append(document, previous_digest)
        latest = self.read()
        candidate_sha = f"{document['revision']}:{self._digest(document)}"
        if latest.content_sha != candidate_sha:
            raise ConcurrentUpdate("another queue mutation won the same revision; retry against canonical state")
        return candidate_sha

    def compare_and_swap(self, document: dict[str, Any], expected_sha: str) -> str:
        if not isinstance(document, dict):
            raise ValueError("queue document must be an object")
        if not expected_sha:
            raise ValueError("expected_sha is required; blind writes are prohibited")
        current = self.read()
        return self._compare_and_swap_from_snapshot(document, expected_sha, current)

    def mutate(
        self,
        mutator: Callable[[dict[str, Any]], tuple[dict[str, Any], Any]],
        *,
        max_conflicts: int = 5,
    ) -> Any:
        if not callable(mutator):
            raise ValueError("mutator must be callable")
        if isinstance(max_conflicts, bool) or not isinstance(max_conflicts, int) or max_conflicts < 0:
            raise ValueError("max_conflicts must be a non-negative integer")
        for attempt in range(max_conflicts + 1):
            snapshot = self._ensure_bootstrap()
            candidate, result = mutator(copy.deepcopy(snapshot.document))
            if not isinstance(candidate, dict):
                raise ValueError("mutator must return a queue document object")
            if candidate == snapshot.document:
                return result
            try:
                self._compare_and_swap_from_snapshot(candidate, snapshot.content_sha, snapshot)
                return result
            except ConcurrentUpdate:
                if attempt >= max_conflicts:
                    raise
        raise ConcurrentUpdate("queue update conflict budget exhausted")
