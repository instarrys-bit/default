import hashlib
import io
import zipfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import importlib.util
HELPER_PATH = ROOT / ".github" / "workflow_helpers" / "restore_audit_state_from_cas.py"
SPEC = importlib.util.spec_from_file_location("restore_audit_state_from_cas", HELPER_PATH)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)
reconstruct_archive = HELPER.reconstruct_archive
unwrap_artifact_payload = HELPER.unwrap_artifact_payload


class FakeStore:
    def __init__(self, objects):
        self.objects = objects
        self.read_ids = []

    def read(self, record_id):
        self.read_ids.append(record_id)
        return self.objects[record_id]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RestoreAuditStateFromCASTests(unittest.TestCase):
    def fixture(self):
        first = b"first-segment:"
        second = b"second-segment"
        archive = first + second
        first_id = digest(b"manifest-one")
        second_id = digest(b"manifest-two")
        catalog = {
            "source_run_id": 42243792540,
            "source_workflow_path": ".github/workflows/auto_sync.yml",
            "all_artifacts_verified": True,
            "artifacts": [{
                "name": "deterministic-audit-output",
                "verified": True,
                "archive_sha256": digest(archive),
                "size_in_bytes": len(archive),
                "segments": [
                    {"segment_index": 0, "manifest_record_id": first_id,
                     "content_sha256": digest(first), "size_in_bytes": len(first)},
                    {"segment_index": 1, "manifest_record_id": second_id,
                     "content_sha256": digest(second), "size_in_bytes": len(second)},
                ],
            }],
        }
        return catalog, FakeStore({first_id: first, second_id: second}), archive

    def test_reconstructs_ordered_segments_and_verifies_full_archive(self):
        catalog, store, expected = self.fixture()
        self.assertEqual(reconstruct_archive(catalog, store, expected_run_id="42243792540"), expected)
        self.assertEqual(len(store.read_ids), 2)

    def test_rejects_catalog_for_another_run(self):
        catalog, store, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, "run ID"):
            reconstruct_archive(catalog, store, expected_run_id="999")

    def test_rejects_unverified_catalog_or_artifact(self):
        catalog, store, _ = self.fixture()
        catalog["all_artifacts_verified"] = False
        with self.assertRaisesRegex(ValueError, "all artifacts"):
            reconstruct_archive(catalog, store, expected_run_id="42243792540")
        catalog["all_artifacts_verified"] = True
        catalog["artifacts"][0]["verified"] = False
        with self.assertRaisesRegex(ValueError, "not verified"):
            reconstruct_archive(catalog, store, expected_run_id="42243792540")

    def test_rejects_missing_or_duplicate_segment_indexes(self):
        catalog, store, _ = self.fixture()
        catalog["artifacts"][0]["segments"][1]["segment_index"] = 0
        with self.assertRaisesRegex(ValueError, "missing, duplicated"):
            reconstruct_archive(catalog, store, expected_run_id="42243792540")

    def test_rejects_tampered_segment(self):
        catalog, store, _ = self.fixture()
        store.objects[store.read_ids[0] if store.read_ids else catalog["artifacts"][0]["segments"][0]["manifest_record_id"]] = b"tampered"
        with self.assertRaisesRegex(ValueError, "failed content verification"):
            reconstruct_archive(catalog, store, expected_run_id="42243792540")

    def test_unwraps_github_artifact_zip_envelope(self):
        payload = b"\x1f\x8b" + b"compressed-tar-payload"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("audit-output.tar.gz", payload)
        self.assertEqual(unwrap_artifact_payload(buffer.getvalue()), payload)

    def test_accepts_direct_gzip_archive(self):
        payload = b"\x1f\x8b" + b"direct-tar-payload"
        self.assertEqual(unwrap_artifact_payload(payload), payload)

    def test_rejects_unexpected_zip_contents(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr("unexpected.bin", b"data")
        with self.assertRaisesRegex(ValueError, "exactly one audit-output.tar.gz"):
            unwrap_artifact_payload(buffer.getvalue())

    def test_rejects_wrong_whole_archive_digest(self):
        catalog, store, _ = self.fixture()
        catalog["artifacts"][0]["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "whole-file SHA-256"):
            reconstruct_archive(catalog, store, expected_run_id="42243792540")


if __name__ == "__main__":
    unittest.main()
