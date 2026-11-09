import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_dashboard_snapshot import build_dead_letter_metrics, build_source_pipeline_metrics


class DashboardDeadLetterMetricsTests(unittest.TestCase):
    def test_cancelled_dead_letters_are_not_counted_as_failures(self):
        tasks = [
            {"status": "DEAD_LETTER", "last_error": {
                "evidence": {"conclusion": "failure"}
            }},
            {"status": "DEAD_LETTER", "last_error": {
                "evidence": {"conclusion": "cancelled"}
            }},
            {"status": "DEAD_LETTER", "last_error": {"type": "unknown"}},
            {"status": "CANCELLED", "last_error": {
                "evidence": {"conclusion": "cancelled"}
            }},
            {"status": "SUCCEEDED"},
        ]
        self.assertEqual(build_dead_letter_metrics(tasks), {
            "dead_letter_failures": 1,
            "dead_letter_cancelled": 1,
            "dead_letter_unclassified": 1,
        })


class DashboardSourcePipelineMetricsTests(unittest.TestCase):
    def test_keeps_active_sources_separate_from_discovery_and_assessment(self):
        result = build_source_pipeline_metrics(
            {"candidate_count": 1557, "candidates": [{}, {}]},
            {"assessments": [{}, {}, {}]},
            {"candidate_count": 43, "eligible_candidate_count": 32, "candidates": [{}]},
            {
                "repository_count": 120,
                "source_file_count": 480,
                "pending_assessment_count": 480,
                "repositories": [],
                "source_files": [],
            },
        )
        self.assertEqual(result, {
            "discovered_repository_count": 1557,
            "assessed_file_count": 3,
            "source_candidate_count": 43,
            "eligible_candidate_count": 32,
            "durable_repository_count": 120,
            "durable_source_file_count": 480,
            "pending_assessment_count": 480,
            "registry_published": True,
        })

    def test_missing_durable_registry_is_not_reported_as_zero_discoveries(self):
        result = build_source_pipeline_metrics(
            {"candidate_count": 12, "candidates": []},
            {"assessments": []},
            {"candidate_count": 4, "eligible_candidate_count": 1, "candidates": []},
            {},
        )
        self.assertEqual(result["discovered_repository_count"], 12)
        self.assertEqual(result["source_candidate_count"], 4)
        self.assertEqual(result["durable_repository_count"], 0)
        self.assertFalse(result["registry_published"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
