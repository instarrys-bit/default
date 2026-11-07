import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_rulesets import source_evidence_eligible_ids


class SourceQuarantineQualityGateTests(unittest.TestCase):
    def test_current_sources_remain_eligible(self):
        inventory = [
            {"id": "direct-a", "status": "CURRENT"},
            {"id": "proxy-a"},
        ]
        self.assertEqual(source_evidence_eligible_ids(inventory), {"direct-a", "proxy-a"})

    def test_quarantined_source_is_excluded_from_evidence(self):
        inventory = [
            {"id": "direct-a", "status": "CURRENT"},
            {"id": "reject-stale", "status": "STALE_QUARANTINED"},
        ]
        self.assertEqual(source_evidence_eligible_ids(inventory), {"direct-a"})

    def test_unknown_source_status_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown source quality status"):
            source_evidence_eligible_ids([{"id": "source-x", "status": "SUSPENDED"}])

    def test_duplicate_or_missing_source_identity_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source inventory identity"):
            source_evidence_eligible_ids([{"status": "CURRENT"}])
        with self.assertRaisesRegex(ValueError, "duplicate source inventory identity"):
            source_evidence_eligible_ids([
                {"id": "source-x", "status": "CURRENT"},
                {"id": "source-x", "status": "STALE_QUARANTINED"},
            ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
