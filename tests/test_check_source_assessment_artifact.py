import hashlib
import io
import json
import sys
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "workflow_helpers"))

import check_source_assessment_artifact as artifact_helper
from check_source_assessment_artifact import verify_assessment_archive


class AssessmentArtifactVerifierTests(unittest.TestCase):
    def setUp(self):
        self.expected = {
            "workflow_run_id": "42417075148",
            "workflow_head_sha": "bfefa68fa01644be240780dad8945b7a49274ebb",
            "artifact_sha256": "b" * 64,
        }
        self.producer_run = {
            "id": 90000000001,
            "path": ".github/workflows/automation-watchdog.yml",
            "head_branch": "main",
            "head_sha": "14e6e3933d99e5b15b155b7f8a0f4325c0487725",
            "status": "completed",
            "conclusion": "success",
        }
        self.contents = {
            "data/source_assessments_runtime.json": b'{"activation_count":0,"assessments":[]}\n',
            "sources/source_assessments.json": b'{"assessment_count":0,"assessments":[]}\n',
            "reports/source-assessment.md": b"# Source assessment\n",
        }

    def make_archive(self, activation_count=0, predecessor=None, producer_run_id=None, producer_path=None, tamper_file=False):
        files = [
            {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
            for path, content in sorted(self.contents.items())
        ]
        manifest_sha = hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        proof = {
            "schema_version": 1,
            "assessment_task_id": "task_assessment",
            "task_status": "SUCCEEDED",
            "verification_status": "passed",
            "artifact_verification": {"valid": True, "activation_count": activation_count},
            "predecessor": predecessor or {
                "program_id": "script_discover_sources",
                "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
                "workflow_run_id": self.expected["workflow_run_id"],
                "workflow_head_sha": self.expected["workflow_head_sha"],
                "artifact_path": "sources/discovered_sources.json",
                "artifact_sha256": self.expected["artifact_sha256"],
            },
            "producer_workflow_path": producer_path or ".github/workflows/automation-watchdog.yml",
            "producer_workflow_run_id": str(producer_run_id or self.producer_run["id"]),
            "producer_workflow_head_sha": self.producer_run["head_sha"],
            "files": files,
            "artifact_sha256": manifest_sha,
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, content in self.contents.items():
                archive.writestr(path, b"tampered\n" if tamper_file and path == "reports/source-assessment.md" else content)
            archive.writestr("source-assessment-proof.json", json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n")
        blob = output.getvalue()
        artifact = {
            "id": 12345,
            "name": "source-assessment-output",
            "expired": False,
            "digest": "sha256:" + hashlib.sha256(blob).hexdigest(),
            "workflow_run": {"id": self.producer_run["id"], "head_sha": self.producer_run["head_sha"], "head_branch": "main"},
        }
        return blob, artifact, proof

    def test_accepts_exact_immutable_non_activating_assessment_artifact(self):
        blob, artifact, _ = self.make_archive()
        result = verify_assessment_archive(blob, artifact, self.producer_run, self.expected)
        self.assertEqual(result["artifact_id"], 12345)
        self.assertEqual(result["producer_workflow_run_id"], str(self.producer_run["id"]))

    def test_rejects_source_activation(self):
        blob, artifact, _ = self.make_archive(activation_count=1)
        with self.assertRaisesRegex(ValueError, "source activation"):
            verify_assessment_archive(blob, artifact, self.producer_run, self.expected)

    def test_rejects_wrong_discovery_predecessor(self):
        predecessor = {
            "program_id": "script_discover_sources",
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": "42417075148",
            "workflow_head_sha": "0" * 40,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": self.expected["artifact_sha256"],
        }
        blob, artifact, _ = self.make_archive(predecessor=predecessor)
        with self.assertRaisesRegex(ValueError, "exact verified Discovery predecessor"):
            verify_assessment_archive(blob, artifact, self.producer_run, self.expected)

    def test_rejects_tampered_assessment_file(self):
        blob, artifact, _ = self.make_archive(tamper_file=True)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_assessment_archive(blob, artifact, self.producer_run, self.expected)

    def test_rejects_wrong_artifact_owner_workflow(self):
        blob, artifact, _ = self.make_archive(producer_path=".github/workflows/source-discovery.yml")
        wrong_run = dict(self.producer_run, path=".github/workflows/source-discovery.yml")
        with self.assertRaisesRegex(ValueError, "workflow path"):
            verify_assessment_archive(blob, artifact, wrong_run, self.expected)

    def test_rejects_missing_artifact_zip_digest(self):
        blob, artifact, _ = self.make_archive()
        artifact["digest"] = None
        with self.assertRaisesRegex(ValueError, "valid ZIP SHA-256 digest"):
            verify_assessment_archive(blob, artifact, self.producer_run, self.expected)

    def test_rejects_mismatched_artifact_zip_digest(self):
        blob, artifact, _ = self.make_archive()
        artifact["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match GitHub artifact metadata"):
            verify_assessment_archive(blob, artifact, self.producer_run, self.expected)



    def test_skips_untrusted_producer_runs_before_downloading_artifacts(self):
        artifacts = [
            {
                "id": 1,
                "name": artifact_helper.ASSESSMENT_ARTIFACT_NAME,
                "expired": False,
                "workflow_run": {"id": 101, "head_branch": "feature", "head_sha": "a" * 40},
            },
            {
                "id": 2,
                "name": artifact_helper.ASSESSMENT_ARTIFACT_NAME,
                "expired": False,
                "workflow_run": {"id": 102, "head_branch": "main", "head_sha": "b" * 40},
            },
            {
                "id": 3,
                "name": artifact_helper.ASSESSMENT_ARTIFACT_NAME,
                "expired": False,
                "workflow_run": {"id": 103, "head_branch": "main", "head_sha": "c" * 40},
            },
        ]
        failed_run = {
            "id": 102,
            "path": artifact_helper.ASSESSMENT_WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": "b" * 40,
            "status": "completed",
            "conclusion": "failure",
        }
        successful_run = {
            "id": 103,
            "path": artifact_helper.ASSESSMENT_WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": "c" * 40,
            "status": "completed",
            "conclusion": "success",
        }
        proof = {"predecessor": {"workflow_run_id": self.expected["workflow_run_id"]}}
        with (
            patch.object(artifact_helper, "_get_json", side_effect=[{"artifacts": artifacts}, failed_run, successful_run]),
            patch.object(artifact_helper, "_get_bytes", return_value=b"verified-archive") as get_bytes,
            patch.object(artifact_helper, "_proof_from_archive", return_value=("source-assessment-proof.json", proof)),
            patch.object(artifact_helper, "verify_assessment_archive", return_value={"verified": True}),
        ):
            result = artifact_helper.find_matching_assessment_artifact("owner/repo", "token", self.expected)
        self.assertTrue(result["found"])
        self.assertTrue(result["verified"])
        get_bytes.assert_called_once_with(
            f"{artifact_helper.API_ROOT}/repos/owner/repo/actions/artifacts/3/zip",
            "token",
            max_bytes=artifact_helper.MAX_ASSESSMENT_ARCHIVE_BYTES,
        )


    def test_artifact_redirect_does_not_forward_github_token_to_storage(self):
        api_url = "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip"
        headers = Message()
        headers["Location"] = "https://objects.example.test/signed/artifact.zip"
        redirect = urllib.error.HTTPError(api_url, 302, "Found", headers, io.BytesIO())
        opener = unittest.mock.Mock()
        opener.open.side_effect = redirect
        payload = b"verified-zip"
        with (
            patch.object(artifact_helper.urllib.request, "build_opener", return_value=opener),
            patch.object(artifact_helper.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as storage_open,
        ):
            result = artifact_helper._get_bytes(api_url, "github-secret", max_bytes=100)

        self.assertEqual(result, payload)
        api_request = opener.open.call_args.args[0]
        storage_request = storage_open.call_args.args[0]
        self.assertEqual(api_request.get_header("Authorization"), "Bearer github-secret")
        self.assertIsNone(storage_request.get_header("Authorization"))
        self.assertEqual(storage_request.full_url, "https://objects.example.test/signed/artifact.zip")

    def test_api_response_size_limit_is_enforced(self):
        opener = unittest.mock.Mock()
        opener.open.return_value = io.BytesIO(b"1234")
        with patch.object(artifact_helper.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "safety limit"):
                artifact_helper._get_bytes("https://api.github.com/test", "token", max_bytes=3)

    def test_redirect_without_location_fails_closed(self):
        headers = Message()
        redirect = urllib.error.HTTPError(
            "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip",
            302, "Found", headers, io.BytesIO(),
        )
        opener = unittest.mock.Mock()
        opener.open.side_effect = redirect
        with patch.object(artifact_helper.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "no signed location"):
                artifact_helper._get_bytes(
                    "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip",
                    "token",
                )


if __name__ == "__main__":
    unittest.main()
