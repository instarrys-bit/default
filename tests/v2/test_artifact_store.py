import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from artifact_store import (
    ArtifactError, FilesystemArtifactStore, build_manifest,
    manifest_record_id, verify_manifest,
)


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


if __name__ == "__main__":
    unittest.main()
