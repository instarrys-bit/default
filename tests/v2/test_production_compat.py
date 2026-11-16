import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))
from production_compat import run_builder, stage_candidate
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


class ProductionCompatTests(unittest.TestCase):
    def test_current_deterministic_builder_runs_in_isolated_workspace(self):
        uu_conf = ROOT / "modules" / "uu.conf"
        before = sha256(uu_conf.read_bytes())
        candidate = run_builder(
            ROOT,
            as_of="2026-11-17T00:00:00Z",
            source_revision="a" * 40,
        )
        after = sha256(uu_conf.read_bytes())
        self.assertEqual(before, after)
        self.assertEqual(candidate["uu_conf_sha256"], before)
        self.assertFalse(candidate["uu_conf_modified"])
        self.assertEqual(candidate["candidate_status"], "VALIDATED_NOT_PUBLISHED")
        self.assertEqual(candidate["publication_status"], "NOT_PUBLISHED")
        self.assertEqual(candidate["activation_count"], 0)
        self.assertEqual(candidate["output_file_count"], 7)
        self.assertEqual({x["path"] for x in candidate["output_files"]}, {
            "rulesets/direct.list",
            "rulesets/proxy.list",
            "rulesets/reject.list",
            "rulesets/manifest.json",
            "rulesets/pending_queue.json",
            "rulesets/reject_review_queue.json",
            "reports/reject-secondary-review.md",
        })
        self.assertEqual(len(candidate["builder_bundle_sha256"]), 64)
        self.assertTrue(candidate["ruleset_baseline_snapshot"])

    def test_candidate_staging_requires_a_live_lease_guard(self):
        backend = MemoryCASBackend()
        store = ContentAddressedArtifactStore(backend)
        calls = []
        def guard():
            proof = {
                "task_id":"task_prod",
                "task_lease_id":"task-lease",
                "owner":"production-worker",
                "resource_key":"storage/v2/artifacts",
                "resource_lease_id":"artifact-lease",
                "fencing_token":7,
            }
            calls.append(proof)
            return proof
        candidate = {
            "source_revision":"a" * 40,
            "output_total_bytes":32,
            "output_files":[
                {"path":"rulesets/direct.list","content":b"DOMAIN,a.example","sha256":sha256(b"DOMAIN,a.example"),"size_bytes":16},
                {"path":"rulesets/proxy.list","content":b"DOMAIN,b.example","sha256":sha256(b"DOMAIN,b.example"),"size_bytes":16},
            ],
        }
        result = stage_candidate(candidate, store, task_id="task_prod", lease_guard=guard)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["output_file_count"], 2)
        self.assertEqual(result["publication_status"], "NOT_PUBLISHED")
        manifest = json.loads(store.read(result["candidate_record_id"]))
        self.assertEqual(manifest["storage_lease_proof"]["fencing_token"], 7)
        self.assertNotIn("token", json.dumps(manifest))


if __name__ == "__main__":
    unittest.main()
