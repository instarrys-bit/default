import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import assess_sources
import task_scheduler
import verify_assess_sources_artifacts


class CheckpointMemoryStore:
    def __init__(self, document):
        self.document = document

    def read(self):
        import copy
        return type("Snapshot", (), {"document": copy.deepcopy(self.document)})()

    def mutate(self, mutator):
        import copy
        candidate, result = mutator(copy.deepcopy(self.document))
        if candidate != self.document:
            self.document = candidate
        return result


class AssessSourcesTaskInputTests(unittest.TestCase):
    def checkpoint_fixture(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        task_id = "task_" + "a" * 24
        proof = {
            "logical/production-pipeline": {"lease_id": "pipeline-lease", "fencing_token": 4},
            "logical/source-assessment-checkpoints": {"lease_id": "history-lease", "fencing_token": 7},
        }
        task_token = "task-lease-token"
        predecessor = {"artifact_sha256": "b" * 64, "workflow_run_id": "123"}
        task = {
            "task_id": task_id, "target_program_id": "script_assess_sources",
            "input": {"predecessor": predecessor},
            "status": "CLAIMED",
            "lease": {"owner": "worker-test", "token": task_token,
                      "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")},
            "resource_lease": {"status": "ACTIVE", "resources": proof},
        }
        resource_leases = {}
        for key, item in proof.items():
            resource_leases[key] = {
                "status": "ACTIVE", "task_id": task_id, "worker_id": "worker-test",
                "task_lease_token": task_token, **item,
                "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
            }
        store = CheckpointMemoryStore({
            "schema_version": 1, "revision": 0, "tasks": [task],
            "resource_leases": resource_leases,
        })
        env = {
            "AUTOMATION_TASK_ID": task_id,
            "AUTOMATION_WORKER_ID": "worker-test",
            "AUTOMATION_TASK_LEASE_TOKEN": task_token,
            "AUTOMATION_RESOURCE_LEASE_PROOF": json.dumps(proof),
        }
        return store, env, predecessor

    def test_each_completed_url_is_durably_checkpointed_and_restored(self):
        store, env, predecessor = self.checkpoint_fixture()
        item = {
            "url": "https://raw.githubusercontent.com/example/repo/main/list.txt",
            "repository": "example/repo", "parser_candidate": "domain-only",
            "domain_fingerprints": ["abc123"],
        }
        with patch.dict("os.environ", env, clear=True), \
             patch.object(assess_sources, "assert_resource_lease_from_environment"), \
             patch("remote_task_queue_runtime.validate_candidate"):
            assess_sources.persist_assessment_checkpoint(
                "discovery-run:123:" + predecessor["artifact_sha256"][:12],
                predecessor, item, store=store, registry={},
            )
            restored = assess_sources.load_assessment_checkpoint(
                "discovery-run:123:" + predecessor["artifact_sha256"][:12],
                predecessor, store=store, registry={},
            )
        self.assertEqual(restored[item["url"]], item)
        saved = store.document["tasks"][0]["assessment_checkpoint"]
        self.assertEqual(saved["last_successful_url"], item["url"])
        self.assertEqual(len(saved["completed"]), 1)

    def test_checkpoint_rejects_stale_fencing_token(self):
        store, env, predecessor = self.checkpoint_fixture()
        item = {"url": "https://raw.githubusercontent.com/example/repo/main/list.txt"}
        store.document["resource_leases"]["logical/source-assessment-checkpoints"]["fencing_token"] = 8
        with patch.dict("os.environ", env, clear=True), \
             patch.object(assess_sources, "assert_resource_lease_from_environment"), \
             patch("remote_task_queue_runtime.validate_candidate"):
            with self.assertRaisesRegex(ValueError, "fencing proof is stale"):
                assess_sources.persist_assessment_checkpoint(
                    "discovery-run:123:" + predecessor["artifact_sha256"][:12],
                    predecessor, item, store=store, registry={},
                )

    def test_legacy_workflow_defaults_are_bounded_to_one_resumable_batch(self):
        self.assertEqual(assess_sources.load_task_options(None), {
            "max_urls": 20,
            "max_file_bytes": 1_000_000,
            "max_total_bytes": 10_000_000,
        })
    def test_independent_assessment_writes_only_runner_local_artifacts(self):
        source = (ROOT / "scripts" / "assess_sources.py").read_text(encoding="utf-8")
        self.assertIn('AUTOMATION_ARTIFACT_ROOT', source)
        self.assertIn('AUTOMATION_PREDECESSOR_ARTIFACT_ROOT', source)
        self.assertIn('write_document(RUNTIME_OUTPUT, result, "assessments", lease_required=False)', source)
        self.assertIn('write_document(OUTPUT, compact_assessment_result(persistent), "assessments", lease_required=False)', source)
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn('"AUTOMATION_QUEUE_SNAPSHOT": str(snapshot_path)', scheduler)
        self.assertIn('"AUTOMATION_RESOURCE_LEASE_PROOF"', scheduler)
        self.assertIn('"AUTOMATION_QUEUE_TOKEN": store.token', scheduler)
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "script_assess_sources")
        self.assertEqual(adapter["write_resources"], [])
        self.assertEqual(adapter["publish_resources"], [])
        self.assertEqual(adapter["resource_contract"]["resource_keys"],
                         ["logical/production-pipeline", "logical/source-assessment-checkpoints", "logical/source-dag-supervision"])

    def test_verified_discovery_artifact_is_resolved_from_runner_temp(self):
        with tempfile.TemporaryDirectory() as repository_dir, tempfile.TemporaryDirectory() as runner_dir:
            repository = Path(repository_dir)
            artifact_root = Path(runner_dir) / "source-discovery-output"
            artifact = artifact_root / "sources" / "discovered_sources.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text('{"candidates":[]}\\n', encoding="utf-8")
            with patch.dict("os.environ", {
                "RUNNER_TEMP": runner_dir,
                "AUTOMATION_PREDECESSOR_ARTIFACT_ROOT": str(artifact_root),
            }, clear=True):
                digest = task_scheduler.read_only_resource_digests(
                    repository, ["sources/discovered_sources.json"]
                )["sources/discovered_sources.json"]
            self.assertIsNotNone(digest)
            self.assertEqual(digest, task_scheduler.read_only_resource_digests(
                artifact_root, ["sources/discovered_sources.json"]
            )["sources/discovered_sources.json"])

    def test_accepts_bounded_independent_task_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps({
                "max_urls": 20, "max_file_bytes": 1_000_000, "max_total_bytes": 10_000_000,
                "predecessor": {
                    "program_id": "script_discover_sources",
                    "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
                    "workflow_run_id": "41770000000",
                    "workflow_head_sha": "a" * 40,
                    "artifact_path": "sources/discovered_sources.json",
                    "artifact_sha256": "b" * 64,
                },
            }), encoding="utf-8")
            self.assertEqual(assess_sources.load_task_options(path)["max_urls"], 20)

    def test_rejects_missing_extra_boolean_and_unbounded_options(self):
        invalid = [
            {"max_urls": 10, "max_file_bytes": 1000},
            {"max_urls": 10, "max_file_bytes": 1000, "max_total_bytes": 2000, "unexpected": 1},
            {"max_urls": True, "max_file_bytes": 1000, "max_total_bytes": 2000},
            {"max_urls": 21, "max_file_bytes": 1000, "max_total_bytes": 2000},
            {"max_urls": 10, "max_file_bytes": 3000, "max_total_bytes": 2000},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for value in invalid:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        assess_sources.load_task_options(path)


class AssessSourcesArtifactVerifierTests(unittest.TestCase):
    def test_verifies_runtime_history_and_report_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime.json"
            persistent = root / "persistent.json"
            report = root / "report.md"
            item = {"url": "https://raw.githubusercontent.com/example/repo/main/list.txt",
                    "repository": "example/repo", "parser_candidate": "domain-only",
                    "policy_candidate": "DIRECT", "domain_fingerprints": ["ephemeral"]}
            runtime.write_text(json.dumps({
                "assessment_count": 1, "assessed_this_run_count": 1,
                "total_bytes_read": 123, "activation_count": 0,
                "assessments": [item],
            }), encoding="utf-8")
            persistent.write_text(json.dumps({
                "assessment_count": 1, "assessments": [
                    {k: v for k, v in item.items() if k != "domain_fingerprints"}
                ],
            }), encoding="utf-8")
            report.write_text("# Source assessment\n", encoding="utf-8")
            result_path = root / "result.json"
            result_path.write_text(json.dumps({
                "assessed": 1, "bytes_read": 123, "parser_candidates": 1,
                "policy_candidates": 1, "activated": 0,
            }), encoding="utf-8")
            with patch.object(verify_assess_sources_artifacts, "ROOT", root), \
                 patch.object(verify_assess_sources_artifacts, "RUNTIME", runtime), \
                 patch.object(verify_assess_sources_artifacts, "PERSISTENT", persistent), \
                 patch.object(verify_assess_sources_artifacts, "REPORT", report):
                self.assertTrue(verify_assess_sources_artifacts.verify(result_path)["valid"])

    def test_read_only_digest_tracks_sharded_document_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logical = root / "sources" / "discovered_sources.json"
            logical.parent.mkdir(parents=True)
            manifest = logical.with_name(logical.name + ".manifest.json")
            shard_dir = logical.parent / (logical.name + ".parts-test")
            shard_dir.mkdir()
            shard = shard_dir / "part-000000.jsonl"
            shard.write_text('{"url":"https://example.com"}\\n', encoding="utf-8")
            manifest.write_text(json.dumps({
                "schema_version": 1, "format": "jsonl-shards-v1",
                "logical_path": logical.name, "collection_key": "candidates",
                "record_count": 1, "shard_directory": shard_dir.name,
                "shards": [{"file": shard.name}],
            }), encoding="utf-8")
            before = task_scheduler.read_only_resource_digests(root, ["sources/discovered_sources.json"])
            shard.write_text('{"url":"https://changed.example"}\\n', encoding="utf-8")
            after = task_scheduler.read_only_resource_digests(root, ["sources/discovered_sources.json"])
            self.assertNotEqual(before, after)

    def test_scheduler_protects_declared_read_only_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sources" / "domain_sources.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"sources":[]}', encoding="utf-8")
            before = task_scheduler.read_only_resource_digests(root, ["sources/domain_sources.json"])
            task_scheduler.ensure_read_only_resources_unchanged(before, root)
            path.write_text('{"sources":[{"url":"new"}]}', encoding="utf-8")
            with self.assertRaisesRegex(task_scheduler.ProtectedConfigMutationError, "read-only resources"):
                task_scheduler.ensure_read_only_resources_unchanged(before, root)

    def test_scheduler_task_id_filter_is_exact_and_does_not_expand_eligibility(self):
        eligible = {"task_assessment", "task_production"}
        self.assertEqual(task_scheduler.filter_eligible_task_ids(eligible, "task_assessment"), {"task_assessment"})
        self.assertEqual(task_scheduler.filter_eligible_task_ids(eligible, "task_unknown"), set())
        self.assertEqual(task_scheduler.filter_eligible_task_ids(eligible), eligible)
        with self.assertRaises(ValueError):
            task_scheduler.run_scheduler_once(
                object(), {}, {}, worker_id="canary-worker", task_id=""
            )

    def test_generated_python_cache_is_excluded_from_artifact_workspace(self):
        self.assertTrue(task_scheduler.is_generated_python_cache_path(
            "scripts/__pycache__/task_scheduler.cpython-311.pyc"
        ))
        self.assertFalse(task_scheduler.is_generated_python_cache_path(
            "sources/source_assessments.json"
        ))
        self.assertEqual(task_scheduler.safe_child_environment(task_scheduler.ROOT)["PYTHONDONTWRITEBYTECODE"], "1")

    def test_scheduler_task_id_filter_rejects_whitespace(self):
        with self.assertRaises(ValueError):
            task_scheduler.filter_eligible_task_ids({"task_assessment"}, "   ")

    def test_artifact_publication_allowlist_excludes_ephemeral_and_protected_files(self):
        persistent = "sources/source_assessments.json"
        self.assertTrue(task_scheduler.publishable_resource_path(persistent, [persistent]))
        self.assertTrue(task_scheduler.publishable_resource_path(
            persistent + ".manifest.json", [persistent]
        ))
        self.assertTrue(task_scheduler.publishable_resource_path(
            persistent + ".parts-0123456789abcdef/part-000000.jsonl", [persistent]
        ))
        self.assertFalse(task_scheduler.publishable_resource_path(
            persistent + ".parts.tmp-abc/part-000000.jsonl", [persistent]
        ))
        self.assertFalse(task_scheduler.publishable_resource_path(
            "data/source_assessments_runtime.json", [persistent]
        ))
        self.assertFalse(task_scheduler.publishable_resource_path(
            "modules/uu.conf", [persistent]
        ))

    def test_task_mode_requires_lease_proof(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires an active resource lease proof"):
                assess_sources.assert_optional_write_lease(assess_sources.RUNTIME_OUTPUT, required=True)

    def test_verifier_rejects_missing_empty_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime.json"
            persistent = root / "persistent.json"
            report = root / "report.md"
            result_path = root / "result.json"
            result_path.write_text(json.dumps({
                "assessed": 0, "bytes_read": 0, "parser_candidates": 0,
                "policy_candidates": 0, "activated": 0,
            }), encoding="utf-8")
            with patch.object(verify_assess_sources_artifacts, "ROOT", root), \
                 patch.object(verify_assess_sources_artifacts, "RUNTIME", runtime), \
                 patch.object(verify_assess_sources_artifacts, "PERSISTENT", persistent), \
                 patch.object(verify_assess_sources_artifacts, "REPORT", report):
                with self.assertRaisesRegex(ValueError, "required assessment artifact is missing"):
                    verify_assess_sources_artifacts.verify(result_path)

    def test_rejects_any_source_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime.json"
            persistent = root / "persistent.json"
            report = root / "report.md"
            runtime.write_text(json.dumps({
                "assessment_count": 0, "assessed_this_run_count": 0,
                "total_bytes_read": 0, "activation_count": 1, "assessments": [],
            }), encoding="utf-8")
            persistent.write_text(json.dumps({"assessment_count": 0, "assessments": []}), encoding="utf-8")
            report.write_text("report", encoding="utf-8")
            result_path = root / "result.json"
            result_path.write_text(json.dumps({
                "assessed": 0, "bytes_read": 0, "parser_candidates": 0,
                "policy_candidates": 0, "activated": 0,
            }), encoding="utf-8")
            with patch.object(verify_assess_sources_artifacts, "ROOT", root), \
                 patch.object(verify_assess_sources_artifacts, "RUNTIME", runtime), \
                 patch.object(verify_assess_sources_artifacts, "PERSISTENT", persistent), \
                 patch.object(verify_assess_sources_artifacts, "REPORT", report):
                with self.assertRaisesRegex(ValueError, "never activate"):
                    verify_assess_sources_artifacts.verify(result_path)


if __name__ == "__main__":
    unittest.main()
