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


class AssessSourcesTaskInputTests(unittest.TestCase):
    def test_default_limits_preserve_existing_workflow_behavior(self):
        self.assertEqual(assess_sources.load_task_options(None), {
            "max_urls": assess_sources.MAX_URLS,
            "max_file_bytes": assess_sources.MAX_BYTES,
            "max_total_bytes": assess_sources.MAX_TOTAL_BYTES,
        })

    def test_assessor_fences_each_logical_output_before_writing(self):
        source = (ROOT / "scripts" / "assess_sources.py").read_text(encoding="utf-8")
        for target in ("RUNTIME_OUTPUT", "OUTPUT", "REPORT"):
            self.assertIn(f"assert_optional_write_lease({target}, required=args.task_input is not None)", source)
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn('"AUTOMATION_QUEUE_SNAPSHOT": str(snapshot_path)', scheduler)
        self.assertIn('"AUTOMATION_RESOURCE_LEASE_PROOF"', scheduler)
        self.assertIn('"AUTOMATION_QUEUE_TOKEN": store.token', scheduler)

    def test_accepts_bounded_independent_task_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps({
                "max_urls": 20, "max_file_bytes": 1_000_000, "max_total_bytes": 10_000_000,
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
        self.assertEqual(eligible & {"task_assessment"}, {"task_assessment"})
        self.assertFalse(eligible & {"task_unknown"})
        with self.assertRaises(ValueError):
            task_scheduler.run_scheduler_once(
                object(), {}, {}, worker_id="canary-worker", task_id=""
            )

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
            "shadowrocket/ss.conf", [persistent]
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
