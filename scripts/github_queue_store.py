#!/usr/bin/env python3
"""GitHub Contents API persistence with SHA compare-and-swap for task queues.

This module is a storage adapter only. It does not dispatch workflows, execute
programs, grant permissions, or decide whether a task may be completed.
"""
from __future__ import annotations


import base64
import copy
import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class QueueStoreError(RuntimeError):
    """Base error for remote queue storage."""


class ConcurrentUpdate(QueueStoreError):
    """The file SHA changed between read and write; caller must re-read."""


class GitHubAPIError(QueueStoreError):
    """GitHub rejected or could not complete a queue storage request."""


@dataclass(frozen=True)
class QueueSnapshot:
    document: dict[str, Any]
    content_sha: str


class GitHubContentsQueueStore:
    """A single-document CAS store backed by a repository file.

    All writers must use this adapter (or equivalent SHA-guarded writes).
    Mutators are re-run after a conflict and therefore must be deterministic
    and side-effect-free. Use task idempotency keys for enqueue operations.
    """

    def __init__(
        self,
        repository: str,
        path: str = "automation/task_queue.json",
        *,
        branch: str = "main",
        token: str | None = None,
        api_url: str = "https://api.github.com",
        timeout: int = 15,
    ) -> None:
        if not repository or "/" not in repository:
            raise ValueError("repository must be owner/name")
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("path must be a safe repository-relative path")
        if not branch:
            raise ValueError("branch is required")
        self.repository = repository
        self.path = path
        self.branch = branch
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        encoded_path = quote(self.path, safe="/")
        return f"{self.api_url}/repos/{self.repository}/contents/{encoded_path}"

    def _request(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise GitHubAPIError("GitHub token is required; token value was not logged")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shadowrocket-automation-queue",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(self.endpoint, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            # Contents API reports stale SHA writes as 409 or, in some cases,
            # 422 with an explicit SHA-mismatch message.
            detail = exc.read(2048).decode("utf-8", errors="replace").lower()
            if exc.code == 409 or (exc.code == 422 and ("sha" in detail or "does not match" in detail)):
                raise ConcurrentUpdate("queue file changed; re-read before retrying") from None
            raise GitHubAPIError(f"GitHub Contents API returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise GitHubAPIError("GitHub Contents API request failed or timed out") from None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubAPIError("GitHub Contents API returned invalid JSON") from None
        if not isinstance(value, dict):
            raise GitHubAPIError("GitHub Contents API response must be an object")
        return value

    def read(self) -> QueueSnapshot:
        response = self._request("GET")
        content = response.get("content")
        sha = response.get("sha")
        if not isinstance(content, str) or not isinstance(sha, str) or not sha:
            raise GitHubAPIError("queue file response is missing content or blob SHA")
        try:
            raw = base64.b64decode(content, validate=False)
            document = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubAPIError("stored task queue is not valid UTF-8 JSON") from None
        if not isinstance(document, dict):
            raise GitHubAPIError("stored task queue must be a JSON object")
        return QueueSnapshot(document=document, content_sha=sha)

    def compare_and_swap(self, document: dict[str, Any], expected_sha: str) -> str:
        if not isinstance(document, dict):
            raise ValueError("queue document must be an object")
        if not expected_sha:
            raise ValueError("expected_sha is required; blind writes are prohibited")
        content = base64.b64encode(
            (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).decode("ascii")
        response = self._request("PUT", {
            "message": "Update durable automation task queue",
            "content": content,
            "sha": expected_sha,
            "branch": self.branch,
        })
        result = response.get("content")
        new_sha = result.get("sha") if isinstance(result, dict) else None
        if not isinstance(new_sha, str) or not new_sha:
            raise GitHubAPIError("queue update response is missing the new blob SHA")
        return new_sha

    def mutate(
        self,
        mutator: Callable[[dict[str, Any]], tuple[dict[str, Any], Any]],
        *,
        max_conflicts: int = 5,
    ) -> Any:
        """Apply a pure mutation, retrying only explicit SHA conflicts."""
        if not callable(mutator):
            raise ValueError("mutator must be callable")
        if isinstance(max_conflicts, bool) or not isinstance(max_conflicts, int) or max_conflicts < 0:
            raise ValueError("max_conflicts must be a non-negative integer")
        for attempt in range(max_conflicts + 1):
            snapshot = self.read()
            candidate, result = mutator(copy.deepcopy(snapshot.document))
            if not isinstance(candidate, dict):
                raise ValueError("mutator must return a queue document object")
            if candidate == snapshot.document:
                return result
            try:
                self.compare_and_swap(candidate, snapshot.content_sha)
                return result
            except ConcurrentUpdate:
                if attempt >= max_conflicts:
                    raise
        raise ConcurrentUpdate("queue update conflict budget exhausted")
