import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_dashboard_snapshot import build_dead_letter_metrics


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
