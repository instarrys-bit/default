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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


MARKER = "<!-- shadowrocket-automation-queue:v1 -->"
MARKER_V2 = "<!-- shadowrocket-automation-queue:v2 -->"
INDEX_MARKER = "<!-- shadowrocket-automation-queue-index:v1 -->"
DEFAULT_ISSUE_NUMBER = 423
DEFAULT_INDEX_ISSUE_NUMBER = 571
QUEUE_ROTATE_COMMENT_THRESHOLD = 2400
MAX_COMMENT_BYTES = 60_000
CHUNK_DATA_CHARS = 40_000
COMMENT_PAGE_BATCH_SIZE = 4


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
        index_issue_number: int | None = None,
        rotate_comment_threshold: int = QUEUE_ROTATE_COMMENT_THRESHOLD,
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
        if issue_number is None and self.issue_number == 315:
            raise ValueError("durable queue Issue #315 is retired; use Issue #423")
        if index_issue_number is not None:
            self.index_issue_number = int(index_issue_number)
        elif issue_number is None:
            raw_index = os.environ.get(
                "AUTOMATION_QUEUE_INDEX_ISSUE_NUMBER", str(DEFAULT_INDEX_ISSUE_NUMBER)
            )
            try:
                self.index_issue_number = int(raw_index)
            except (TypeError, ValueError):
                raise ValueError("AUTOMATION_QUEUE_INDEX_ISSUE_NUMBER must be a positive integer") from None
        else:
            self.index_issue_number = None
        if self.index_issue_number is not None and self.index_issue_number < 1:
            raise ValueError("AUTOMATION_QUEUE_INDEX_ISSUE_NUMBER must be a positive integer")
        if (
            isinstance(rotate_comment_threshold, bool)
            or not isinstance(rotate_comment_threshold, int)
            or rotate_comment_threshold < 1
            or rotate_comment_threshold > 2500
        ):
            raise ValueError("rotate_comment_threshold must be an integer from 1 through 2500")
        self.rotate_comment_threshold = rotate_comment_threshold
        self.active_pointer: dict[str, Any] | None = None
        self._last_comments: list[dict[str, Any]] = []
        self.bootstrap_path = bootstrap_path or os.environ.get("AUTOMATION_QUEUE_BOOTSTRAP_PATH") or (
            "automation/task_queue_rebuild_seed.json"
            if self.issue_number == DEFAULT_ISSUE_NUMBER else path
        )
        if not self.bootstrap_path or ".." in self.bootstrap_path.split("/"):
            raise ValueError("bootstrap_path must be a safe path")

    @property
    def comments_endpoint(self) -> str:
        return f"{self.api_url}/repos/{self.repository}/issues/{self.issue_number}/comments"

    @property
    def index_comments_endpoint(self) -> str:
        if self.index_issue_number is None:
            raise GitHubAPIError("queue index is not configured")
        return f"{self.api_url}/repos/{self.repository}/issues/{self.index_issue_number}/comments"

    @property
    def issues_endpoint(self) -> str:
        return f"{self.api_url}/repos/{self.repository}/issues"

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
        # Only idempotent reads are retried. A POST may have reached GitHub even
        # when the client times out, so retrying it could append duplicate queue
        # snapshots and break the canonical comment chain.
        attempt = 0
        max_get_attempts = 7
        while True:
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                break
            except HTTPError as exc:
                if exc.code == 409:
                    raise ConcurrentUpdate("queue snapshot append conflicted; re-read before retrying") from None
                error_body = b""
                try:
                    error_body = exc.read(4096)
                except OSError:
                    pass
                error_text = error_body.decode("utf-8", errors="replace")
                error_lower = error_text.lower()
                headers = exc.headers or {}
                secondary_limited = (
                    exc.code == 403
                    and (
                        headers.get("X-RateLimit-Remaining") == "0"
                        or "secondary rate limit" in error_lower
                        or "rate limit exceeded" in error_lower
                        or "abuse detection" in error_lower
                    )
                )
                retryable = method == "GET" and (
                    exc.code in {429, 500, 502, 503, 504} or secondary_limited
                )
                if retryable and attempt + 1 < max_get_attempts:
                    retry_after = headers.get("Retry-After")
                    reset_at = headers.get("X-RateLimit-Reset") if secondary_limited else None
                    try:
                        if retry_after:
                            delay = float(retry_after)
                        elif reset_at and headers.get("X-RateLimit-Remaining") == "0":
                            delay = max(0.0, float(reset_at) - time.time())
                        else:
                            delay = min(0.5 * (2 ** attempt), 4.0)
                    except (TypeError, ValueError):
                        delay = min(0.5 * (2 ** attempt), 4.0)
                    time.sleep(max(0.0, min(delay, 120.0)))
                    attempt += 1
                    continue
                # Preserve the server's diagnostic message without exposing the
                # Authorization header or request payload. This is essential for
                # distinguishing missing token scope from primary/secondary limits.
                try:
                    decoded_error = json.loads(error_text) if error_text else {}
                except json.JSONDecodeError:
                    decoded_error = {}
                server_message = decoded_error.get("message") if isinstance(decoded_error, dict) else None
                if not isinstance(server_message, str):
                    server_message = error_text.strip().replace("\\n", " ")[:800]
                else:
                    server_message = server_message.strip()[:800]
                endpoint = url.split("?", 1)[0].replace(self.api_url, "")
                diagnostics = [
                    f"{method} {endpoint}",
                    f"HTTP {exc.code}",
                ]
                if server_message:
                    diagnostics.append(f"message={server_message}")
                request_id = headers.get("X-GitHub-Request-Id")
                if request_id:
                    diagnostics.append(f"request_id={request_id}")
                remaining = headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    diagnostics.append(f"rate_limit_remaining={remaining}")
                retry_after = headers.get("Retry-After")
                if retry_after:
                    diagnostics.append(f"retry_after={retry_after}")
                if secondary_limited:
                    diagnostics.append("classification=rate_limit")
                raise GitHubAPIError("GitHub Issues API " + "; ".join(diagnostics)) from None
            except (URLError, TimeoutError, OSError):
                if method == "GET" and attempt + 1 < max_get_attempts:
                    time.sleep(min(0.5 * (2 ** attempt), 4.0))
                    attempt += 1
                    continue
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

    def _fetch_comment_page(self, page: int, issue_number: int | None = None) -> list[Any]:
        target_issue = self.issue_number if issue_number is None else issue_number
        query = urlencode({"per_page": 100, "page": page})
        endpoint = f"{self.api_url}/repos/{self.repository}/issues/{target_issue}/comments"
        result = self._request("GET", f"{endpoint}?{query}")
        if not isinstance(result, list):
            raise GitHubAPIError("GitHub Issue comments response must be an array")
        return result

    def _all_comments(self, issue_number: int | None = None) -> list[dict[str, Any]]:
        """Read the complete append-only history without serial page latency.

        The hash chain is still validated over every returned comment. Fetching
        bounded page batches concurrently keeps each CAS read practical as the
        durable Issue history grows, while preserving ascending page order.
        """
        first_page = self._fetch_comment_page(1, issue_number)
        comments = [item for item in first_page if isinstance(item, dict)]
        if len(first_page) < 100:
            return comments

        page = 2
        with ThreadPoolExecutor(max_workers=COMMENT_PAGE_BATCH_SIZE) as executor:
            while True:
                pages = range(page, page + COMMENT_PAGE_BATCH_SIZE)
                results = list(executor.map(
                    lambda current_page: self._fetch_comment_page(current_page, issue_number),
                    pages,
                ))
                reached_end = False
                for result in results:
                    comments.extend(item for item in result if isinstance(item, dict))
                    if len(result) < 100:
                        reached_end = True
                        break
                if reached_end:
                    break
                page += COMMENT_PAGE_BATCH_SIZE
        return comments

    def _post_comment(self, body: str, issue_number: int | None = None) -> int:
        if len(body.encode("utf-8")) > MAX_COMMENT_BYTES:
            raise GitHubAPIError("queue snapshot chunk exceeds the safe GitHub comment size")
        target_issue = self.issue_number if issue_number is None else issue_number
        endpoint = f"{self.api_url}/repos/{self.repository}/issues/{target_issue}/comments"
        result = self._request("POST", endpoint, {"body": body})
        comment_id = result.get("id") if isinstance(result, dict) else None
        if isinstance(comment_id, bool) or not isinstance(comment_id, int):
            raise GitHubAPIError("GitHub Issue comment response is missing its numeric ID")
        return comment_id

    def _append(
        self, document: dict[str, Any], previous_sha256: str | None,
        issue_number: int | None = None,
    ) -> int:
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
            return self._post_comment(legacy_body, issue_number=issue_number)
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
            self._post_comment(MARKER_V2 + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":")), issue_number=issue_number)
        commit = {
            "schema_version": 2, "kind": "commit", "revision": revision,
            "previous_sha256": previous_sha256, "sha256": digest,
            "encoding": "gzip+base64", "total": total,
        }
        return self._post_comment(MARKER_V2 + "\n" + json.dumps(commit, sort_keys=True, separators=(",", ":")), issue_number=issue_number)

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

    @classmethod
    def _decode_index_pointer(cls, comment: dict[str, Any]) -> dict[str, Any] | None:
        body = comment.get("body")
        if not isinstance(body, str) or not body.startswith(INDEX_MARKER + "\n"):
            return None
        try:
            payload = json.loads(body.split("\n", 1)[1])
            epoch = payload.get("epoch")
            issue_number = payload.get("issue_number")
            revision = payload.get("revision", payload.get("source_revision"))
            snapshot_sha = payload.get("snapshot_sha256", payload.get("source_snapshot_sha256"))
            previous = payload.get("previous_sha256")
            digest = payload.get("sha256")
            comment_id = comment.get("id")
            if (
                payload.get("schema_version") != 1
                or isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1
                or isinstance(issue_number, bool) or not isinstance(issue_number, int) or issue_number < 1
                or isinstance(revision, bool) or not isinstance(revision, int) or revision < 0
                or not isinstance(snapshot_sha, str) or len(snapshot_sha) != 64
                or (previous is not None and (not isinstance(previous, str) or len(previous) != 64))
                or not isinstance(digest, str) or len(digest) != 64
                or isinstance(comment_id, bool) or not isinstance(comment_id, int)
            ):
                raise ValueError("invalid queue index pointer fields")
            unsigned = {key: value for key, value in payload.items() if key != "sha256"}
            if hashlib.sha256(cls._canonical_bytes(unsigned)).hexdigest() != digest:
                raise ValueError("queue index pointer digest mismatch")
            if "source_issue_number" in payload and payload["source_issue_number"] != issue_number:
                raise ValueError("queue index source issue differs from active issue")
            if "source_revision" in payload and payload["source_revision"] != revision:
                raise ValueError("queue index source revision differs from checkpoint revision")
            if "source_snapshot_sha256" in payload and payload["source_snapshot_sha256"] != snapshot_sha:
                raise ValueError("queue index source snapshot digest differs from checkpoint digest")
            return {
                "epoch": epoch,
                "issue_number": issue_number,
                "revision": revision,
                "snapshot_sha256": snapshot_sha,
                "previous_sha256": previous,
                "sha256": digest,
                "comment_id": comment_id,
                "payload": payload,
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GitHubAPIError(f"invalid durable queue index pointer: {exc}") from None

    @classmethod
    def _canonical_index_pointer(cls, comments: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = []
        for comment in comments:
            pointer = cls._decode_index_pointer(comment)
            if pointer is not None:
                candidates.append(pointer)
        if not candidates:
            return None
        by_epoch: dict[int, list[dict[str, Any]]] = {}
        for pointer in candidates:
            by_epoch.setdefault(pointer["epoch"], []).append(pointer)
        initial = [
            pointer for pointer in by_epoch.get(1, [])
            if pointer["previous_sha256"] is None
        ]
        if not initial:
            raise GitHubAPIError("durable queue index has no epoch-1 genesis pointer")
        current = min(initial, key=lambda item: item["comment_id"])
        while True:
            following = [
                pointer for pointer in by_epoch.get(current["epoch"] + 1, [])
                if pointer["previous_sha256"] == current["sha256"]
            ]
            if not following:
                break
            current = min(following, key=lambda item: item["comment_id"])
        if any(pointer["epoch"] > current["epoch"] for pointer in candidates):
            raise GitHubAPIError("durable queue index contains an unlinked epoch pointer")
        return current

    def _read_index_pointer(self) -> dict[str, Any] | None:
        if self.index_issue_number is None:
            return None
        return self._canonical_index_pointer(self._all_comments(self.index_issue_number))

    def _resolve_active_issue(self) -> dict[str, Any] | None:
        pointer = self._read_index_pointer()
        self.active_pointer = pointer
        if pointer is not None:
            self.issue_number = pointer["issue_number"]
        return pointer

    def _snapshot_matches_pointer(
        self, comments: list[dict[str, Any]], pointer: dict[str, Any]
    ) -> bool:
        for comment in comments:
            decoded = self._decode_comment(comment)
            if decoded is None:
                decoded = self._decode_v2_commit(comment, comments)
            if decoded is None:
                continue
            revision, _previous, digest, _document = decoded
            if revision == pointer["revision"] and digest == pointer["snapshot_sha256"]:
                return True
        return False

    def _read_issue_snapshot(
        self, issue_number: int
    ) -> tuple[QueueSnapshot | None, list[dict[str, Any]]]:
        comments = self._all_comments(issue_number)
        snapshot = self._canonical_snapshot(comments)
        return snapshot, comments

    def _make_index_pointer(
        self, *, epoch: int, issue_number: int, document: dict[str, Any],
        previous_sha256: str | None,
    ) -> dict[str, Any]:
        unsigned = {
            "schema_version": 1,
            "epoch": epoch,
            "issue_number": issue_number,
            "revision": document["revision"],
            "snapshot_sha256": self._digest(document),
            "previous_sha256": previous_sha256,
        }
        return {
            **unsigned,
            "sha256": hashlib.sha256(self._canonical_bytes(unsigned)).hexdigest(),
        }

    def _append_index_pointer(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.index_issue_number is None:
            raise GitHubAPIError("queue index is not configured")
        current = self._read_index_pointer()
        if current is not None:
            if (
                current["epoch"] == payload["epoch"]
                and current["revision"] == payload["revision"]
                and current["snapshot_sha256"] == payload["snapshot_sha256"]
                and current["previous_sha256"] == payload["previous_sha256"]
            ):
                return current
            if (
                current["epoch"] + 1 != payload["epoch"]
                or current["sha256"] != payload["previous_sha256"]
            ):
                raise ConcurrentUpdate("queue epoch index advanced while a rotation was being prepared")
        elif payload["epoch"] != 1 or payload["previous_sha256"] is not None:
            raise ConcurrentUpdate("queue epoch index genesis changed while a rotation was being prepared")
        body = INDEX_MARKER + "\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self._post_comment(body, issue_number=self.index_issue_number)
        resolved = self._read_index_pointer()
        if resolved is None or resolved["epoch"] < payload["epoch"]:
            raise GitHubAPIError("queue epoch index pointer was not visible after append")
        if resolved["epoch"] == payload["epoch"] and resolved["previous_sha256"] != payload["previous_sha256"]:
            raise GitHubAPIError("queue epoch index resolved to a different predecessor chain")
        return resolved

    def _find_or_create_epoch_issue(
        self, epoch: int, snapshot: QueueSnapshot
    ) -> tuple[int, str]:
        digest = self._digest(snapshot.document)
        revision = snapshot.document["revision"]
        title = f"Durable automation queue epoch {epoch} revision {revision} {digest[:12]}"
        marker = f"<!-- shadowrocket-automation-queue-epoch:v1 key={epoch}:{revision}:{digest} -->"
        query = f'repo:{self.repository} is:issue in:title "{title}"'
        search_url = f"{self.api_url}/search/issues?{urlencode({'q': query, 'per_page': 100})}"
        search = self._request("GET", search_url)
        items = search.get("items", []) if isinstance(search, dict) else []
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("title") == title
                and marker in str(item.get("body") or "")
                and isinstance(item.get("number"), int)
            ):
                return item["number"], marker
        body = "\n".join([
            "Append-only durable automation queue epoch.",
            marker,
            f"Checkpoint revision: {revision}",
            f"Checkpoint SHA-256: {digest}",
            f"Previous active issue: #{self.issue_number}",
            "This is an exact checkpoint of the prior epoch. Task IDs and lifecycle states are preserved; no task is replayed.",
        ])
        created = self._request("POST", self.issues_endpoint, {"title": title, "body": body})
        number = created.get("number") if isinstance(created, dict) else None
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise GitHubAPIError("GitHub did not return a numeric queue epoch issue number")
        return number, marker

    def _ensure_epoch_snapshot(self, issue_number: int, snapshot: QueueSnapshot) -> None:
        existing, _comments = self._read_issue_snapshot(issue_number)
        expected_sha = f"{snapshot.document['revision']}:{self._digest(snapshot.document)}"
        if existing is None:
            self._append(snapshot.document, None, issue_number=issue_number)
            existing, _comments = self._read_issue_snapshot(issue_number)
        if (
            existing is None
            or existing.content_sha != expected_sha
            or existing.document != snapshot.document
        ):
            raise GitHubAPIError("new queue epoch does not contain the exact source checkpoint")

    def _rotate_epoch_if_needed(
        self, snapshot: QueueSnapshot, comments: list[dict[str, Any]]
    ) -> QueueSnapshot:
        if self.index_issue_number is None or len(comments) < self.rotate_comment_threshold:
            return snapshot
        pointer = self.active_pointer or self._read_index_pointer()
        if pointer is None:
            pointer = self._append_index_pointer(
                self._make_index_pointer(
                    epoch=1,
                    issue_number=self.issue_number,
                    document=snapshot.document,
                    previous_sha256=None,
                )
            )
        if pointer["issue_number"] != self.issue_number:
            self.issue_number = pointer["issue_number"]
            active_snapshot, active_comments = self._read_issue_snapshot(self.issue_number)
            if active_snapshot is None:
                raise GitHubAPIError("active queue epoch has no canonical snapshot")
            if active_snapshot.content_sha != snapshot.content_sha:
                raise ConcurrentUpdate("queue advanced while resolving the active epoch")
            self._last_comments = active_comments
            return self._rotate_epoch_if_needed(active_snapshot, active_comments)
        next_epoch = pointer["epoch"] + 1
        new_issue_number, _marker = self._find_or_create_epoch_issue(next_epoch, snapshot)
        self._ensure_epoch_snapshot(new_issue_number, snapshot)
        next_pointer = self._make_index_pointer(
            epoch=next_epoch,
            issue_number=new_issue_number,
            document=snapshot.document,
            previous_sha256=pointer["sha256"],
        )
        resolved = self._append_index_pointer(next_pointer)
        self.active_pointer = resolved
        self.issue_number = resolved["issue_number"]
        new_snapshot, new_comments = self._read_issue_snapshot(self.issue_number)
        if (
            new_snapshot is None
            or new_snapshot.content_sha != snapshot.content_sha
            or new_snapshot.document != snapshot.document
        ):
            raise GitHubAPIError("active queue epoch differs from the checkpoint that was rotated")
        self._last_comments = new_comments
        return new_snapshot

    def read(self) -> QueueSnapshot:
        pointer = self._resolve_active_issue()
        comments = self._all_comments()
        self._last_comments = comments
        snapshot = self._canonical_snapshot(comments)
        if pointer is not None:
            if (
                snapshot is None
                or snapshot.document.get("revision", -1) < pointer["revision"]
                or not self._snapshot_matches_pointer(comments, pointer)
            ):
                raise GitHubAPIError("active queue epoch does not contain its indexed checkpoint")
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
        if self.index_issue_number is not None:
            current = self._rotate_epoch_if_needed(current, self._last_comments)
            if current.content_sha != expected_sha:
                raise ConcurrentUpdate("queue revision changed while rotating the active epoch")
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
