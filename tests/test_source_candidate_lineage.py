import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_source_candidates import assessment_input_path, build_matrix, merge_assessment_inventory
from discover_sources import preserve_current_discovery_snapshot


class SourceCandidateLineagePolicyTests(unittest.TestCase):
    def _assessment(self, repo, fingerprints=None, archived=False):
        return {
            "repository": repo,
            "policy_candidate": "DIRECT",
            "parser_candidate": "shadowrocket-domain-rules",
            "policy_evidence": "explicit_third_field",
            "exact_domain_count": 100,
            "suffix_domain_count": 0,
            "adblock_domain_count": 0,
            "domain_only_count": 0,
            "domain_fingerprints": fingerprints if fingerprints is not None else [f"{i:032x}" for i in range(100)],
            "url": "https://example.test/list",
            "duplicate_domain_lines": 0,
            "sha256": "f" * 64,
            "drift": {},
            "archived": archived,
        }

    def test_unverified_lineage_and_shared_readme_refs_are_warnings_not_vetoes(self):
        assessments = {"assessments": [self._assessment("publisher/a")]}
        lineage = {
            "candidate_sources": [{
                "repository": "publisher/a",
                "lineage_status": "unverified",
                "status": "partial",
                "reference_count": 3,
            }],
            "candidate_shared_reference_pairs": [{
                "repositories": ["publisher/a", "publisher/b"],
                "shared_readme_references": ["shared/upstream"],
            }],
        }
        result = build_matrix(assessments, lineage)
        candidate = result["candidates"][0]
        self.assertTrue(candidate["activation_eligible"])
        self.assertEqual(candidate["activation_blockers"], [])
        self.assertEqual(candidate["domain_fingerprint_count"], 100)
        self.assertTrue(candidate["fingerprints_complete"])
        self.assertEqual(candidate["lineage_warning"], "possible_shared_readme_references; correlation signal only")



    def test_candidate_matrix_combines_stable_sources_from_separate_batches(self):
        url_a = "https://raw.githubusercontent.com/publisher/a/main/clash-rules/list.list"
        url_b = "https://raw.githubusercontent.com/publisher/b/main/clash-rules/list.list"
        url_stale = "https://raw.githubusercontent.com/publisher/old/main/clash-rules/list.list"
        fingerprints_a = [f"{i:032x}" for i in range(100)]
        fingerprints_b = [f"{i + 1000:032x}" for i in range(100)]

        def saved(repo, url, digest, fingerprints):
            return {
                "repository": repo,
                "url": url,
                "sha256": digest,
                "parser_candidate": "shadowrocket-domain-rules",
                "parser_version": 2,
                "policy_candidate": "DIRECT",
                "policy_evidence": "explicit_third_field",
                "exact_domain_count": 100,
                "suffix_domain_count": 0,
                "adblock_domain_count": 0,
                "domain_only_count": 0,
                "domain_fingerprints": fingerprints,
                "drift": {"status": "unchanged"},
                "assessed_at": "2026-11-24T00:00:00Z",
            }

        registry = {
            "repositories": [
                {"repository": "publisher/a", "archived": False, "stars": 20},
                {"repository": "publisher/b", "archived": False, "stars": 30},
                {"repository": "publisher/old", "archived": False, "stars": 5},
            ],
            "source_files": [
                {"repository": "publisher/a", "url": url_a, "assessment": saved("publisher/a", url_a, "a" * 64, fingerprints_a)},
                {"repository": "publisher/b", "url": url_b, "assessment": saved("publisher/b", url_b, "b" * 64, fingerprints_b)},
                {"repository": "publisher/old", "url": url_stale, "assessment": saved("publisher/old", url_stale, "c" * 64, [f"{i + 2000:032x}" for i in range(100)])},
            ],
        }
        current = {"assessments": [{
            **saved("publisher/b", url_b, "d" * 64, fingerprints_b),
            "drift": {"status": "unchanged"},
        }]}
        merged = merge_assessment_inventory(current, registry, {url_a, url_b})
        self.assertEqual(len(merged["assessments"]), 2)
        self.assertEqual(
            next(item for item in merged["assessments"] if item["url"] == url_b)["sha256"],
            "d" * 64,
        )
        result = build_matrix(
            merged,
            {"candidate_sources": [], "candidate_shared_reference_pairs": []},
        )
        self.assertEqual(result["policy_summary"]["DIRECT"]["candidate_publishers"], 2)
        self.assertEqual(result["policy_summary"]["DIRECT"]["independent_eligible_groups"], 2)
        self.assertTrue(result["policy_summary"]["DIRECT"]["activation_ready"])



    def test_current_discovery_snapshot_preserves_manifest_and_shards_before_restore(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / "workspace" / "sources"
            source_dir.mkdir(parents=True)
            source = source_dir / "discovered_sources.json"
            source.write_text('{"candidates": []}', encoding="utf-8")
            (source_dir / "discovered_sources.json.manifest.json").write_text(
                '{"schema_version": 2}', encoding="utf-8"
            )
            parts = source_dir / "discovered_sources.json.parts-test"
            parts.mkdir()
            (parts / "part-000000.jsonl").write_text('{"record": 1}\\n', encoding="utf-8")
            env_file = root / "github_env"
            snapshot = preserve_current_discovery_snapshot(source, root / "runner-temp", env_file)
            self.assertTrue((snapshot / "sources/discovered_sources.json").is_file())
            self.assertTrue((snapshot / "sources/discovered_sources.json.manifest.json").is_file())
            self.assertTrue((snapshot / "sources/discovered_sources.json.parts-test/part-000000.jsonl").is_file())
            self.assertIn(
                "AUTOMATION_CURRENT_SOURCE_DISCOVERY_ROOT=" + str(snapshot),
                env_file.read_text(encoding="utf-8"),
            )


    def test_assessment_input_path_reads_verified_artifact_environment(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "assessment-artifact"
            root.mkdir()
            runtime = root / "data" / "source_assessments_runtime.json"
            runtime.parent.mkdir()
            runtime.write_text('{"assessments": []}', encoding="utf-8")
            with patch.dict("os.environ", {
                "AUTOMATION_SOURCE_ASSESSMENT_ROOT": str(root),
                "RUNNER_TEMP": temporary,
            }):
                self.assertEqual(assessment_input_path(), runtime)


    def test_missing_fingerprints_fail_closed_and_do_not_count_as_independent(self):
        result = build_matrix(
            {"assessments": [self._assessment("publisher/a", fingerprints=[])]},
            {"candidate_sources": [], "candidate_shared_reference_pairs": []},
        )
        candidate = result["candidates"][0]
        self.assertFalse(candidate["activation_eligible"])
        self.assertFalse(candidate["fingerprints_complete"])
        self.assertIn("domain_fingerprints_missing_or_invalid", candidate["activation_blockers"])
        self.assertFalse(result["policy_summary"]["DIRECT"]["activation_ready"])

    def test_archived_publisher_remains_blocked(self):
        result = build_matrix(
            {"assessments": [self._assessment("publisher/a", archived=True)]},
            {"candidate_sources": [], "candidate_shared_reference_pairs": []},
        )
        self.assertFalse(result["candidates"][0]["activation_eligible"])
        self.assertIn("publisher_archived", result["candidates"][0]["activation_blockers"])


if __name__ == "__main__":
    unittest.main()
