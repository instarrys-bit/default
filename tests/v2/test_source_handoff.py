import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from source_handoff import validate_handoff, stage_validated_handoff
from artifact_store import ArtifactConflict, ContentAddressedArtifactStore, sha256


class MemoryCASBackend:
    def __init__(self):
        self.objects = {}

    def put_if_absent(self, digest, content):
        if sha256(content) != digest:
            raise ValueError("digest mismatch")
        if digest in self.objects:
            if self.objects[digest] != content:
                raise ArtifactConflict("immutable object conflict")
            return False
        self.objects[digest] = content
        return True

    def get_object(self, digest):
        return self.objects.get(digest)


class SourceHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.discovery = self.root / "discovery"
        self.assessment = self.root / "assessment"
        self.discovery.mkdir()
        self.assessment.mkdir()
        self.discovery_run = "42001"
        self.assessment_run = "42002"
        self.discovery_sha = "a" * 40
        self.assessment_sha = "b" * 40
        self.task_id = "task_" + "c" * 24
        (self.discovery / "sources").mkdir()
        (self.discovery / "reports-source-discovery.md").write_text("discovery report\n")
        document = {
            "producer": {
                "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
                "workflow_run_id": self.discovery_run,
                "workflow_head_sha": self.discovery_sha,
            },
            "candidates": [],
        }
        (self.discovery / "sources" / "discovered_sources.json").write_text(json.dumps(document))
        self.discovery_digest = self._logical_discovery_digest()
        discovery_proof = {
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": self.discovery_run,
            "workflow_head_sha": self.discovery_sha,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": self.discovery_digest,
        }
        (self.discovery / "source-discovery-proof.json").write_text(json.dumps(discovery_proof))
        (self.assessment / "data").mkdir()
        (self.assessment / "sources").mkdir()
        (self.assessment / "reports").mkdir()
        (self.assessment / "data" / "source_assessments_runtime.json").write_text('{"assessments":[]}')
        (self.assessment / "sources" / "source_assessments.json").write_text('{"assessments":[]}')
        (self.assessment / "reports" / "source-assessment.md").write_text("assessment report\n")
        predecessor = {
            "program_id": "script_discover_sources",
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": self.discovery_run,
            "workflow_head_sha": self.discovery_sha,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": self.discovery_digest,
        }
        files = []
        for path in sorted(self.assessment.rglob("*")):
            if path.is_file():
                files.append({"path": path.relative_to(self.assessment).as_posix(),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        artifact_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        proof = {
            "schema_version": 1,
            "assessment_task_id": self.task_id,
            "task_status": "SUCCEEDED",
            "verification_status": "passed",
            "artifact_verification": {"valid": True, "activation_count": 0},
            "predecessor": predecessor,
            "producer_workflow_path": ".github/workflows/automation-watchdog.yml",
            "producer_workflow_run_id": self.assessment_run,
            "producer_workflow_head_sha": self.assessment_sha,
            "files": files,
            "artifact_sha256": artifact_sha,
        }
        (self.assessment / "source-assessment-proof.json").write_text(json.dumps(proof))

    def _logical_discovery_digest(self):
        path = self.discovery / "sources" / "discovered_sources.json"
        digest = hashlib.sha256()
        digest.update(b"legacy-json\0")
        digest.update(path.read_bytes())
        return digest.hexdigest()

    def validate(self):
        return validate_handoff(
            discovery_root=self.discovery,
            assessment_root=self.assessment,
            assessment_task_id=self.task_id,
            discovery_run_id=self.discovery_run,
            discovery_head_sha=self.discovery_sha,
            assessment_run_id=self.assessment_run,
            assessment_head_sha=self.assessment_sha,
        )

    def test_verified_handoff_validates_both_proof_chains(self):
        result = self.validate()
        self.assertEqual(result["file_count"], 7)
        self.assertEqual(result["assessment_task_id"], self.task_id)
        self.assertEqual(result["total_bytes"], sum(x.stat().st_size for x in self.discovery.rglob("*") if x.is_file()) +
                         sum(x.stat().st_size for x in self.assessment.rglob("*") if x.is_file()))

    def test_discovery_digest_tampering_is_rejected(self):
        path = self.discovery / "sources" / "discovered_sources.json"
        path.write_text('{"producer":{},"candidates":[{"url":"tampered"}]}')
        with self.assertRaisesRegex(ValueError, "logical-document digest"):
            self.validate()

    def test_assessment_file_tampering_is_rejected(self):
        path = self.assessment / "reports" / "source-assessment.md"
        path.write_text("tampered\n")
        with self.assertRaisesRegex(ValueError, "file set or SHA-256"):
            self.validate()

    def test_wrong_discovery_predecessor_is_rejected(self):
        proof_path = self.assessment / "source-assessment-proof.json"
        proof = json.loads(proof_path.read_text())
        proof["predecessor"]["workflow_run_id"] = "99999"
        proof_path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError, "predecessor"):
            self.validate()

    def test_staging_is_content_addressed_and_non_activating(self):
        validated = self.validate()
        backend = MemoryCASBackend()
        store = ContentAddressedArtifactStore(backend)
        result = stage_validated_handoff(validated, store)
        self.assertEqual(result["activation_count"], 0)
        self.assertEqual(result["publication_status"], "NOT_PUBLISHED")
        self.assertEqual(result["file_artifact_count"], validated["file_count"])
        manifest = store.read(result["handoff_record_id"])
        handoff = json.loads(manifest)
        self.assertEqual(handoff["assessment_task_id"], self.task_id)
        self.assertEqual(handoff["activation_count"], 0)
        self.assertEqual(len(handoff["staged_artifacts"]), validated["file_count"])

    def test_assessment_manifest_digest_mismatch_is_rejected(self):
        proof_path = self.assessment / "source-assessment-proof.json"
        proof = json.loads(proof_path.read_text())
        proof["artifact_sha256"] = "0" * 64
        proof_path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError, "manifest digest"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
