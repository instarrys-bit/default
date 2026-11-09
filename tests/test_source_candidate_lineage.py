import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_source_candidates import assessment_input_path, build_matrix


class SourceCandidateLineagePolicyTests(unittest.TestCase):
    def _assessment(self, repo, fingerprints=None, archived=False):
        return {
            "repository": repo,
            "policy_candidate": "DIRECT",
            "parser_candidate": "shadowrocket-domain-rules",
            "policy_evidence": "explicit_third_field",
            "exact_domain_count": 2,
            "suffix_domain_count": 1,
            "adblock_domain_count": 0,
            "domain_only_count": 0,
            "domain_fingerprints": fingerprints or ["a" * 16, "b" * 16],
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
        self.assertEqual(candidate["lineage_warning"], "possible_shared_readme_references; correlation signal only")


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


    def test_archived_publisher_remains_blocked(self):
        result = build_matrix(
            {"assessments": [self._assessment("publisher/a", archived=True)]},
            {"candidate_sources": [], "candidate_shared_reference_pairs": []},
        )
        self.assertFalse(result["candidates"][0]["activation_eligible"])
        self.assertIn("publisher_archived", result["candidates"][0]["activation_blockers"])


if __name__ == "__main__":
    unittest.main()
