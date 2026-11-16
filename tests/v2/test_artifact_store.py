import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from artifact_store import (
    ArtifactConflict, ArtifactError, ContentAddressedArtifactStore,
    FilesystemArtifactStore, MAX_ARTIFACT_BYTES, build_manifest,
    manifest_record_id, sha256, verify_manifest,
)



class MemoryCASBackend:
    def __init__(self):
        self.objects = {}

    def put_if_absent(self, digest, content):
        if sha256(content) != digest:
            raise ValueError("digest mismatch")
        existing = self.objects.get(digest)
        if existing is not None:
            if existing != content:
                raise ArtifactConflict("immutable object conflict")
            return False
        self.objects[digest] = content
        return True

    def get_object(self, digest):
        return self.objects.get(digest)


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = FilesystemArtifactStore(self.tmp.name)
        self.provenance = {
            "source_id": "source-a",
            "source_revision": "commit:abc123",
            "task_id": "task-1",
            "producer": "production-worker",
        }

    def test_stage_and_read_chunked_artifact(self):
        payload = (b"shadowrocket-v2-" * 5000) + b"end"
        staged = self.store.stage(payload, artifact_type="domain_candidates",
                                  provenance=self.provenance, chunk_bytes=1024)
        self.assertEqual(staged["artifact_id"], "sha256:" + hashlib.sha256(payload).hexdigest())
        self.assertGreater(staged["chunk_count"], 1)
        self.assertEqual(self.store.read(staged["record_id"]), payload)
        self.assertTrue(self.store.verify(staged["record_id"])["valid"])

    def test_empty_artifact_is_supported(self):
        staged = self.store.stage(b"", artifact_type="empty_payload",
                                  provenance=self.provenance)
        self.assertEqual(self.store.read(staged["record_id"]), b"")
        self.assertEqual(staged["size_bytes"], 0)

    def test_same_content_different_provenance_has_distinct_record(self):
        first = self.store.stage(b"same", artifact_type="candidate",
                                 provenance=self.provenance)
        second_provenance = {**self.provenance, "source_id": "source-b"}
        second = self.store.stage(b"same", artifact_type="candidate",
                                  provenance=second_provenance)
        self.assertEqual(first["artifact_id"], second["artifact_id"])
        self.assertNotEqual(first["record_id"], second["record_id"])

    def test_tampered_chunk_is_detected(self):
        staged = self.store.stage(b"payload", artifact_type="candidate",
                                  provenance=self.provenance)
        chunk_sha = staged["manifest"]["chunks"][0]["sha256"]
        (self.store.chunks_dir / chunk_sha).write_bytes(b"tampered")
        with self.assertRaises(ArtifactError):
            self.store.read(staged["record_id"])

    def test_tampered_manifest_is_detected(self):
        staged = self.store.stage(b"payload", artifact_type="candidate",
                                  provenance=self.provenance)
        path = self.store.manifests_dir / staged["record_id"]
        manifest = json.loads(path.read_text())
        manifest["provenance"]["source_id"] = "forged"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ArtifactError):
            self.store.read(staged["record_id"])

    def test_manifest_verifier_rejects_wrong_chunk(self):
        manifest, _ = build_manifest(b"abc", artifact_type="candidate",
            provenance=self.provenance, schema_version=1, producer_version="test",
            chunk_bytes=2)
        with self.assertRaises(ArtifactError):
            verify_manifest(manifest, lambda _digest: b"x")

    def test_record_id_is_deterministic(self):
        manifest, _ = build_manifest(b"abc", artifact_type="candidate",
            provenance=self.provenance, schema_version=1, producer_version="test")
        self.assertEqual(manifest_record_id(manifest), manifest_record_id(json.loads(json.dumps(manifest))))

    def test_validation_rejects_oversized_chunks(self):
        with self.assertRaises(ValueError):
            build_manifest(b"abc", artifact_type="candidate",
                provenance=self.provenance, schema_version=1,
                producer_version="test", chunk_bytes=99 * 1024 * 1024)


    def test_backend_neutral_cas_store_stages_and_verifies(self):
        backend = MemoryCASBackend()
        store = ContentAddressedArtifactStore(backend)
        payload = b"durable-v2-object" * 500
        staged = store.stage(payload, artifact_type="source_snapshot",
                              provenance=self.provenance, chunk_bytes=256)
        self.assertEqual(store.read(staged["record_id"]), payload)
        self.assertTrue(store.verify(staged["record_id"])["valid"])

    def test_cas_store_deduplicates_chunks_but_preserves_provenance_records(self):
        backend = MemoryCASBackend()
        store = ContentAddressedArtifactStore(backend)
        first = store.stage(b"same-content", artifact_type="candidate",
                            provenance=self.provenance)
        second = store.stage(b"same-content", artifact_type="candidate",
                             provenance={**self.provenance, "source_id":"source-b"})
        self.assertEqual(first["artifact_id"], second["artifact_id"])
        self.assertNotEqual(first["record_id"], second["record_id"])
        self.assertEqual(len([x for x in backend.objects if x == sha256(b"same-content")]), 1)

    def test_cas_store_detects_corrupt_or_missing_objects(self):
        backend = MemoryCASBackend()
        store = ContentAddressedArtifactStore(backend)
        staged = store.stage(b"payload", artifact_type="candidate",
                             provenance=self.provenance)
        chunk = staged["manifest"]["chunks"][0]["sha256"]
        backend.objects[chunk] = b"corrupt"
        with self.assertRaises(ArtifactError):
            store.read(staged["record_id"])
        del backend.objects[chunk]
        with self.assertRaises(FileNotFoundError):
            store.read(staged["record_id"])

    def test_artifact_size_limit_is_enforced(self):
        with patch("artifact_store.MAX_ARTIFACT_BYTES", 3):
            with self.assertRaisesRegex(ValueError, "artifact exceeds"):
                build_manifest(b"four", artifact_type="candidate",
                    provenance=self.provenance, schema_version=1,
                    producer_version="test")



if __name__ == "__main__":
    unittest.main()
