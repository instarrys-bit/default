import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from resolve_source_artifacts import extract, list_assessment_producer_runs, resolve_task, verify_manifest


class SourceArtifactHandoffTests(unittest.TestCase):
    def test_file_manifest_and_aggregate_digest_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'{"assessments": []}\n'
            (root / "runtime.json").write_bytes(payload)
            files = [{"path": "runtime.json", "sha256": hashlib.sha256(payload).hexdigest()}]
            manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            verify_manifest(root, {"files": files, "artifact_sha256": manifest_sha}, "proof.json")

    def test_assessment_producer_scan_reaches_runs_beyond_first_200(self):
        discovery_run_id = "42373818238"
        pages = {
            1: [
                {"id": 43000000000 - index, "path": ".github/workflows/automation-watchdog.yml",
                 "head_branch": "main", "status": "completed", "conclusion": "success"}
                for index in range(100)
            ],
            2: [
                {"id": 42999999900 - index, "path": ".github/workflows/automation-watchdog.yml",
                 "head_branch": "main", "status": "completed", "conclusion": "success"}
                for index in range(100)
            ],
            3: [
                {"id": 42999999700, "path": ".github/workflows/automation-watchdog.yml",
                 "head_branch": "main", "status": "completed", "conclusion": "success"},
                {"id": 42373818238, "path": ".github/workflows/automation-watchdog.yml",
                 "head_branch": "main", "status": "completed", "conclusion": "success"},
                {"id": 42999999699, "path": ".github/workflows/automation-watchdog.yml",
                 "head_branch": "main", "status": "completed", "conclusion": "failure"},
            ],
        }
        requested_pages = []

        def fetch_page(url, token):
            page = int(url.rsplit("page=", 1)[1])
            requested_pages.append(page)
            return {"workflow_runs": pages[page]}

        runs = list_assessment_producer_runs(
            "instarrys-bit/default", "token", discovery_run_id, fetch_page=fetch_page
        )
        self.assertEqual(requested_pages, [1, 2, 3])
        self.assertEqual(len(runs), 201)
        self.assertIn(42999999700, [run["id"] for run in runs])
        self.assertNotIn(42373818238, [run["id"] for run in runs])
        self.assertNotIn(42999999699, [run["id"] for run in runs])

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
