import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dashboard_metrics import build_candidate_review_metrics


class CandidateReviewDashboardMetricsTests(unittest.TestCase):
    def test_distinguishes_candidate_pool_from_unreviewed_candidates(self):
        candidates = [
            {"domain": "seen.example", "classification": "DIRECT"},
            {"domain": "new.example", "classification": "PROXY"},
            {"domain": "SEEN.example.", "classification": "DIRECT"},
        ]
        reviews = [
            {"domain": "seen.example", "status": "REVIEW"},
            {"domain": "historical-only.example", "status": "APPROVED"},
        ]
        result = build_candidate_review_metrics(
            candidates, reviews, {"status": "complete", "candidate_count": 2}, "2026-11-04T00:00:00Z"
        )
        self.assertEqual(result["candidate_total"], 2)
        self.assertEqual(result["history_recorded"], 1)
        self.assertEqual(result["missing_history"], 1)
        self.assertEqual(result["status_counts"], {"REVIEW": 1, "UNREVIEWED": 1})
        self.assertEqual(result["review_ledger_total"], 2)
        self.assertEqual(result["cursor_status"], "complete")

    def test_empty_inputs_are_zero_not_inferred(self):
        result = build_candidate_review_metrics([], [], {})
        self.assertEqual(result["candidate_total"], 0)
        self.assertEqual(result["history_recorded"], 0)
        self.assertEqual(result["missing_history"], 0)
        self.assertEqual(result["status_counts"], {})


if __name__ == "__main__":
    unittest.main()
