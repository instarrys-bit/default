import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_source_candidates import build_matrix


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

    def test_archived_publisher_remains_blocked(self):
        result = build_matrix(
            {"assessments": [self._assessment("publisher/a", archived=True)]},
            {"candidate_sources": [], "candidate_shared_reference_pairs": []},
        )
        self.assertFalse(result["candidates"][0]["activation_eligible"])
        self.assertIn("publisher_archived", result["candidates"][0]["activation_blockers"])


if __name__ == "__main__":
    unittest.main()
