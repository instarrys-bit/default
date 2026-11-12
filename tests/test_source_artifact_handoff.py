import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_source_artifacts import extract, list_assessment_artifact_run_ids, resolve_task, verify_manifest


class SourceArtifactHandoffTests(unittest.TestCase):
    def test_file_manifest_and_aggregate_digest_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'{"assessments": []}\n'
            (root / "runtime.json").write_bytes(payload)
            files = [{"path": "runtime.json", "sha256": hashlib.sha256(payload).hexdigest()}]
            manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            verify_manifest(root, {"files": files, "artifact_sha256": manifest_sha}, "proof.json")

    def test_assessment_artifact_lookup_scans_artifact_pages_and_filters_provenance(self):
        calls = []

        def fake_api_json(url, token):
            page = int(url.rsplit("page=", 1)[1])
            calls.append(page)
            if page == 1:
                return {"artifacts": [
                    {"name": "other-output", "expired": False, "workflow_run": {"id": 10, "head_branch": "main"}},
                    {"name": "source-assessment-output", "expired": True, "workflow_run": {"id": 11, "head_branch": "main"}},
                    {"name": "source-assessment-output", "expired": False, "workflow_run": {"id": 12, "head_branch": "feature"}},
                ] + [{"name": "other-output"}] * 97}
            return {"artifacts": [
                {"name": "source-assessment-output", "expired": False, "workflow_run": {"id": 201, "head_branch": "main"}}
            ]}

        with patch("resolve_source_artifacts.api_json", side_effect=fake_api_json):
            run_ids = list_assessment_artifact_run_ids("owner/repo", "token")

        self.assertEqual(calls, [1, 2])
        self.assertEqual(run_ids, ["201"])

    def test_assessment_artifact_lookup_fails_closed_at_pagination_limit(self):
        with patch(
            "resolve_source_artifacts.api_json",
            return_value={"artifacts": [{"name": "other-output"}] * 100},
        ):
            with self.assertRaisesRegex(ValueError, "10,000-artifact"):
                list_assessment_artifact_run_ids("owner/repo", "token")

    def test_resolver_uses_last_verified_assessment_when_newer_discovery_is_pending(self):
        older = {
            "task_id": "task_discovery_old",
            "target_program_id": "workflow_source_discovery",
            "status": "SUCCEEDED",
            "created_at": "2026-11-07T12:00:00Z",
            "verification": {"status": "passed"},
            "result": {"run_evidence": {"run_id": 42373818238}},
        }
        assessment = {
            "task_id": "task_assessment_old",
            "target_program_id": "script_assess_sources",
            "status": "SUCCEEDED",
            "created_at": "2026-11-07T12:30:00Z",
            "input": {"predecessor": {
                "workflow_run_id": "42373818238",
                "workflow_head_sha": "a" * 40,
                "artifact_path": "sources/discovered_sources.json",
                "artifact_sha256": "b" * 64,
            }},
            "verification": {"status": "passed"},
            "result": {"artifact_verification": {"valid": True, "activation_count": 0}},
        }
        newer = {
            "task_id": "task_discovery_new",
            "target_program_id": "workflow_source_discovery",
            "status": "QUEUED",
            "created_at": "2026-11-08T12:00:00Z",
            "verification": {"status": "passed"},
            "result": {},
        }
        selected, predecessor = resolve_task({"tasks": [older, assessment, newer]})
        self.assertEqual(selected["task_id"], "task_assessment_old")
        self.assertEqual(predecessor["workflow_run_id"], "42373818238")

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
