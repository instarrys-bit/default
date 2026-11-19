#!/usr/bin/env python3
"""Storage Management JSON state store with Contents API SHA-CAS; empty revision-0 queues are valid fresh epochs, not Issue-comment snapshots."""
from __future__ import annotations
import base64, copy, hashlib, json, os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_QUEUE_PATH = "automation/task_queue.json"
ALLOWED_STATE_PATHS = {DEFAULT_QUEUE_PATH, "storage/v2/incidents.json"}
class QueueStoreError(RuntimeError): pass
class ConcurrentUpdate(QueueStoreError): pass
class GitHubAPIError(QueueStoreError): pass

@dataclass(frozen=True)
class QueueSnapshot:
    document: dict[str, Any]
    content_sha: str
    git_blob_sha: str | None = None

def _digest(d):
    return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _logical_sha(d):
    r = d.get("revision")
    if isinstance(r, bool) or not isinstance(r, int):
        raise ValueError("revision must be int")
    return f"{r}:{_digest(d)}"

class GitHubContentsJsonStore:
    def __init__(self, repository, path=DEFAULT_QUEUE_PATH, *, branch="main", token=None, api_url="https://api.github.com", timeout=20, bootstrap_path=None):
        if not repository or "/" not in repository:
            raise ValueError("repository must be owner/name")
        if path not in ALLOWED_STATE_PATHS:
            raise ValueError("Storage Management path is not allowlisted")
        self.repository, self.path, self.branch = repository, path, branch
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api_url, self.timeout = api_url.rstrip("/"), timeout
        self.bootstrap_path = bootstrap_path or path

    @property
    def contents_endpoint(self):
        return f"{self.api_url}/repos/{self.repository}/contents/{self.path}"

    def _request(self, method, url, payload=None):
        if not self.token:
            raise GitHubAPIError("GitHub token required")
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "shadowrocket-storage-management"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except HTTPError as e:
            if e.code == 409:
                raise ConcurrentUpdate("conflict") from None
            raise GitHubAPIError(f"{method} HTTP {e.code} {e.read(400).decode('utf-8','replace')[:300]}") from None
        except (URLError, TimeoutError, OSError) as e:
            raise GitHubAPIError(str(e)) from None
        return json.loads(raw.decode()) if raw else None

    def _read_remote(self):
        try:
            p = self._request("GET", f"{self.contents_endpoint}?ref={self.branch}")
        except GitHubAPIError as e:
            if "HTTP 404" in str(e):
                return None
            raise
        doc = json.loads(base64.b64decode(p["content"].encode("ascii")).decode())
        return QueueSnapshot(document=doc, content_sha=_logical_sha(doc), git_blob_sha=p["sha"])

    def _write_remote(self, document, *, git_blob_sha, message):
        body = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        payload = {"message": message, "content": base64.b64encode(body.encode()).decode("ascii"), "branch": self.branch}
        if git_blob_sha:
            payload["sha"] = git_blob_sha
        r = self._request("PUT", self.contents_endpoint, payload) or {}
        return ((r.get("content") or {}).get("sha"))

    def read(self):
        remote = self._read_remote()
        if remote is not None:
            return remote
        path = Path(self.bootstrap_path)
        if path.is_file():
            return QueueSnapshot(document=json.loads(path.read_text(encoding="utf-8")), content_sha="")
        empty = {"schema_version": 1, "revision": 0}
        if self.path == DEFAULT_QUEUE_PATH:
            empty.update({"tasks": [], "resource_leases": {}})
        else:
            empty.update({"incidents": [], "events": []})
        return QueueSnapshot(document=empty, content_sha="")

    def _ensure_bootstrap(self):
        s = self.read()
        if s.content_sha:
            return s
        d = copy.deepcopy(s.document)
        d.setdefault("schema_version", 1); d.setdefault("revision", 0)
        if self.path == DEFAULT_QUEUE_PATH:
            d.setdefault("tasks", []); d.setdefault("resource_leases", {})
        else:
            d.setdefault("incidents", []); d.setdefault("events", [])
        self._write_remote(d, git_blob_sha=None, message=f"chore(storage): bootstrap {self.path}")
        return self.read()

    def _cas(self, document, expected_sha, current):
        if not expected_sha or not current.content_sha or current.content_sha != expected_sha:
            raise ConcurrentUpdate("sha mismatch")
        if document.get("revision") != current.document["revision"] + 1:
            raise ValueError("revision must advance by one")
        cand = _logical_sha(document)
        self._write_remote(document, git_blob_sha=current.git_blob_sha, message=f"chore(storage): update {self.path} revision {document.get('revision')}")
        if self.read().content_sha != cand:
            raise ConcurrentUpdate("lost race")
        return cand

    def compare_and_swap(self, document, expected_sha):
        return self._cas(document, expected_sha, self.read())

    def mutate(self, mutator, *, max_conflicts=5):
        for i in range(max_conflicts + 1):
            s = self._ensure_bootstrap()
            c, r = mutator(copy.deepcopy(s.document))
            if c == s.document:
                return r
            try:
                self._cas(c, s.content_sha, s); return r
            except ConcurrentUpdate:
                if i >= max_conflicts: raise
        raise ConcurrentUpdate("conflict budget exhausted")


# Backward-compatible import name for existing queue runtime callers.
GitHubContentsQueueStore = GitHubContentsJsonStore
