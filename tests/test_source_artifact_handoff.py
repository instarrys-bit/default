import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_source_artifacts import extract, verify_manifest


class SourceArtifactHandoffTests(unittest.TestCase):
    def test_file_manifest_and_aggregate_digest_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'{"assessments": []}\n'
            (root / "runtime.json").write_bytes(payload)
            files = [{"path": "runtime.json", "sha256": hashlib.sha256(payload).hexdigest()}]
            manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            verify_manifest(root, {"files": files, "artifact_sha256": manifest_sha}, "proof.json")

    def test_modified_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime.json").write_text("original", encoding="utf-8")
            files = [{"path": "runtime.json", "sha256": hashlib.sha256(b"original").hexdigest()}]
            manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            (root / "runtime.json").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_manifest(root, {"files": files, "artifact_sha256": manifest_sha}, "proof.json")

    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime.json").write_text("x", encoding="utf-8")
            (root / "unexpected.json").write_text("y", encoding="utf-8")
            files = [{"path": "runtime.json", "sha256": hashlib.sha256(b"x").hexdigest()}]
            manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with self.assertRaisesRegex(ValueError, "file set"):
                verify_manifest(root, {"files": files, "artifact_sha256": manifest_sha}, "proof.json")

    def test_archive_path_traversal_is_rejected(self):
        import io
        import zipfile
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("../escape.txt", "no")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe artifact path"):
                extract(archive_bytes.getvalue(), Path(directory) / "out")


if __name__ == "__main__":
    unittest.main()
