"""Immutable, content-addressed artifact staging primitives for V2.

The filesystem backend is a storage adapter, not a GitHub repository writer.
Point it at a durable volume/object-store mount in production; never treat an
ephemeral Actions workspace as authoritative storage.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_CHUNK_BYTES = 4 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
GITHUB_OBJECT_ROOT = "storage/v2/artifacts/sha256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactError(RuntimeError):
    """Base class for artifact staging and verification errors."""


class ArtifactConflict(ArtifactError):
    """An immutable object key already exists with different bytes."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_provenance(value: object) -> dict:
    if not isinstance(value, dict) or not value:
        raise ValueError("provenance must be a non-empty object")
    for key in ("source_id", "source_revision", "task_id", "producer"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"provenance.{key} must be a non-empty string")
    return value


def build_manifest(data: bytes, *, artifact_type: str, provenance: dict,
                   schema_version: int, producer_version: str,
                   chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> tuple[dict, list[bytes]]:
    """Build a deterministic manifest and content-addressed chunk payloads."""
    if not isinstance(data, bytes):
        raise TypeError("artifact data must be bytes")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"artifact exceeds {MAX_ARTIFACT_BYTES} byte limit")
    if not isinstance(artifact_type, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,63}", artifact_type):
        raise ValueError("artifact_type must be a 2..64 character lowercase identifier")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version < 1:
        raise ValueError("schema_version must be a positive integer")
    if not isinstance(producer_version, str) or not producer_version.strip():
        raise ValueError("producer_version is required")
    if isinstance(chunk_bytes, bool) or not isinstance(chunk_bytes, int) or not 1 <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError(f"chunk_bytes must be between 1 and {MAX_CHUNK_BYTES}")
    provenance = _validate_provenance(provenance)
    chunks = [data[i:i + chunk_bytes] for i in range(0, len(data), chunk_bytes)]
    if not chunks:
        chunks = [b""]
    manifest = {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "artifact_schema_version": schema_version,
        "producer_version": producer_version,
        "content_sha256": sha256(data),
        "size_bytes": len(data),
        "chunk_bytes": chunk_bytes,
        "chunks": [
            {"sha256": sha256(chunk), "size_bytes": len(chunk), "sequence": i}
            for i, chunk in enumerate(chunks)
        ],
        "provenance": provenance,
    }
    return manifest, chunks


def manifest_record_id(manifest: dict) -> str:
    return sha256(canonical_bytes(manifest))


def verify_manifest(manifest: object, chunk_reader: Callable[[str], bytes]) -> bytes:
    """Verify manifest identity, every chunk, total size and whole-content SHA."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported artifact manifest schema")
    digest = manifest.get("content_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError("invalid content_sha256")
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("artifact manifest must contain at least one chunk")
    output = bytearray()
    for index, entry in enumerate(chunks):
        if not isinstance(entry, dict) or entry.get("sequence") != index:
            raise ValueError("artifact chunk sequence is invalid")
        chunk_sha = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(chunk_sha, str) or not SHA256_RE.fullmatch(chunk_sha):
            raise ValueError("invalid chunk SHA-256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("invalid chunk size")
        chunk = chunk_reader(chunk_sha)
        if not isinstance(chunk, bytes) or len(chunk) != size or sha256(chunk) != chunk_sha:
            raise ArtifactError(f"chunk integrity check failed: {chunk_sha}")
        output.extend(chunk)
    if len(output) != manifest.get("size_bytes") or sha256(bytes(output)) != digest:
        raise ArtifactError("assembled artifact size or SHA-256 mismatch")
    return bytes(output)


class FilesystemArtifactStore:
    """Atomic immutable CAS store; no overwrite or implicit garbage collection."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.chunks_dir = self.root / "chunks" / "sha256"
        self.manifests_dir = self.root / "manifests" / "sha256"
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_create(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".stage-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise ArtifactConflict(f"immutable object collision at {path.name}")
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def put_chunk(self, content: bytes) -> str:
        digest = sha256(content)
        self._atomic_create(self.chunks_dir / digest, content)
        if sha256((self.chunks_dir / digest).read_bytes()) != digest:
            raise ArtifactError("chunk read-back verification failed")
        return digest

    def stage(self, data: bytes, *, artifact_type: str, provenance: dict,
              schema_version: int = 1, producer_version: str = "v2",
              chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> dict:
        manifest, chunks = build_manifest(
            data, artifact_type=artifact_type, provenance=provenance,
            schema_version=schema_version, producer_version=producer_version,
            chunk_bytes=chunk_bytes,
        )
        for chunk, entry in zip(chunks, manifest["chunks"]):
            if self.put_chunk(chunk) != entry["sha256"]:
                raise ArtifactError("chunk address mismatch")
        record_id = manifest_record_id(manifest)
        record = canonical_bytes(manifest) + b"\n"
        self._atomic_create(self.manifests_dir / record_id, record)
        stored = json.loads((self.manifests_dir / record_id).read_text(encoding="utf-8"))
        if manifest_record_id(stored) != record_id:
            raise ArtifactError("manifest read-back verification failed")
        self.read(record_id)
        return {
            "artifact_id": "sha256:" + manifest["content_sha256"],
            "record_id": record_id,
            "content_sha256": manifest["content_sha256"],
            "size_bytes": manifest["size_bytes"],
            "chunk_count": len(chunks),
            "manifest": stored,
        }

    def read(self, record_id: str) -> bytes:
        if not isinstance(record_id, str) or not SHA256_RE.fullmatch(record_id):
            raise ValueError("record_id must be a SHA-256 digest")
        path = self.manifests_dir / record_id
        if not path.is_file():
            raise FileNotFoundError(record_id)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest_record_id(manifest) != record_id:
            raise ArtifactError("manifest record identity mismatch")
        return verify_manifest(manifest, self.get_chunk)

    def get_chunk(self, digest: str) -> bytes:
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError("chunk digest must be SHA-256")
        path = self.chunks_dir / digest
        if not path.is_file():
            raise FileNotFoundError(digest)
        return path.read_bytes()

    def verify(self, record_id: str) -> dict:
        data = self.read(record_id)
        manifest = json.loads((self.manifests_dir / record_id).read_text(encoding="utf-8"))
        return {
            "valid": True,
            "record_id": record_id,
            "content_sha256": manifest["content_sha256"],
            "size_bytes": len(data),
            "chunk_count": len(manifest["chunks"]),
        }


class GitHubContentsObjectBackend:
    """Create-only GitHub Contents API object backend under the V2 SHA allowlist."""

    def __init__(self, repository: str, branch: str, token: str, timeout: int = 30):
        if not isinstance(repository, str) or not re.fullmatch(r"[^/\\s]+/[^/\\s]+", repository):
            raise ValueError("repository must be owner/name")
        if not isinstance(branch, str) or not branch.strip() or not isinstance(token, str) or not token:
            raise ValueError("branch and token are required")
        self.repository = repository
        self.branch = branch
        self.token = token
        self.timeout = timeout
        self.api_root = "https://api.github.com/repos/" + repository
        self.contents_root = self.api_root + "/contents/" + urllib.parse.quote(GITHUB_OBJECT_ROOT, safe="/")

    def _request(self, method: str, url: str, payload: dict | None = None):
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shadowrocket-v2-artifact-store",
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "GET":
                return None
            if exc.code in {409, 422}:
                raise ArtifactConflict(f"GitHub immutable object create conflict ({exc.code})") from None
            detail = exc.read(500).decode("utf-8", "replace")
            raise ArtifactError(f"GitHub Contents API HTTP {exc.code}: {detail[:300]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ArtifactError(f"GitHub Contents API request failed: {exc}") from None
        return json.loads(raw.decode("utf-8")) if raw else None

    def get_object(self, digest: str) -> bytes | None:
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError("object key must be a SHA-256 digest")
        url = self.contents_root + "/" + digest + "?" + urllib.parse.urlencode({"ref": self.branch})
        metadata = self._request("GET", url)
        if metadata is None:
            return None
        encoded = metadata.get("content") if isinstance(metadata, dict) else None
        if metadata.get("encoding") == "base64" and isinstance(encoded, str) and encoded:
            content = base64.b64decode(encoded.encode("ascii"))
        else:
            blob_url = metadata.get("git_url")
            if not isinstance(blob_url, str) or not blob_url.startswith(self.api_root + "/git/blobs/"):
                raise ArtifactError("GitHub Contents response omitted a valid Git blob URL")
            blob = self._request("GET", blob_url)
            if not isinstance(blob, dict) or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
                raise ArtifactError("GitHub Git blob response is not base64 encoded")
            content = base64.b64decode(blob["content"].encode("ascii"))
        if sha256(content) != digest:
            raise ArtifactError("GitHub object content does not match its SHA-256 address")
        return content

    def put_if_absent(self, digest: str, content: bytes) -> bool:
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest) or sha256(content) != digest:
            raise ValueError("object content must match its SHA-256 address")
        path = GITHUB_OBJECT_ROOT + "/" + digest
        url = self.api_root + "/contents/" + urllib.parse.quote(path, safe="/")
        payload = {
            "message": "storage(v2): stage immutable object " + digest[:16],
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        try:
            self._request("PUT", url, payload)
            return True
        except ArtifactConflict:
            existing = self.get_object(digest)
            if existing == content:
                return False
            raise ArtifactConflict("immutable GitHub object key already contains different bytes") from None


class ContentAddressedArtifactStore:
    """Backend-neutral CAS artifact store; manifest is the final commit marker."""

    def __init__(self, repository: str, branch: str, token: str, timeout: int = 30):
        self.backend = GitHubContentsObjectBackend(repository, branch, token, timeout)

    def stage(self, data: bytes, *, artifact_type: str, provenance: dict,
              schema_version: int = 1, producer_version: str = "v2",
              chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> dict:
        manifest, chunks = build_manifest(
            data, artifact_type=artifact_type, provenance=provenance,
            schema_version=schema_version, producer_version=producer_version,
            chunk_bytes=chunk_bytes,
        )
        for chunk, entry in zip(chunks, manifest["chunks"]):
            self.backend.put_if_absent(entry["sha256"], chunk)
        record_id = manifest_record_id(manifest)
        self.backend.put_if_absent(record_id, canonical_bytes(manifest))
        self.read(record_id)
        return {
            "artifact_id": "sha256:" + manifest["content_sha256"],
            "record_id": record_id,
            "content_sha256": manifest["content_sha256"],
            "size_bytes": manifest["size_bytes"],
            "chunk_count": len(chunks),
            "manifest": manifest,
        }

    def read(self, record_id: str) -> bytes:
        if not isinstance(record_id, str) or not SHA256_RE.fullmatch(record_id):
            raise ValueError("record_id must be a SHA-256 digest")
        raw = self.backend.get_object(record_id)
        if raw is None:
            raise FileNotFoundError(record_id)
        if sha256(raw) != record_id:
            raise ArtifactError("manifest record address mismatch")
        manifest = json.loads(raw.decode("utf-8"))
        if canonical_bytes(manifest) != raw or manifest_record_id(manifest) != record_id:
            raise ArtifactError("manifest is not canonical or its record identity is invalid")
        return verify_manifest(manifest, self._get_chunk)

    def _get_chunk(self, digest: str) -> bytes:
        content = self.backend.get_object(digest)
        if content is None:
            raise FileNotFoundError(digest)
        return content

    def verify(self, record_id: str) -> dict:
        data = self.read(record_id)
        raw = self.backend.get_object(record_id)
        manifest = json.loads(raw.decode("utf-8"))
        return {
            "valid": True,
            "record_id": record_id,
            "content_sha256": manifest["content_sha256"],
            "size_bytes": len(data),
            "chunk_count": len(manifest["chunks"]),
        }


class GitHubContentsArtifactStore(ContentAddressedArtifactStore):
    """Durable GitHub Contents API adapter for the V2 artifact object allowlist."""

    def __init__(self, repository: str, branch: str, token: str, timeout: int = 30):
        self.backend = GitHubContentsObjectBackend(repository, branch, token, timeout)
