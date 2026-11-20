from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionIntentReadOnlyTests(unittest.TestCase):
    def test_production_intent_is_read_only_and_never_edits_user_config(self):
        source = (ROOT / "scripts/production_intent.py").read_text(encoding="utf-8")
        self.assertNotIn("--register-ledger", source)
        self.assertNotIn("--merge-observations", source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_document(", source)
        self.assertIn("compute_fingerprint", source)

    def test_unknown_production_input_decisions_fail_closed(self):
        workflow = (ROOT / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("REVIEW_REQUIRED", workflow)
        self.assertIn("block_manifest=true", workflow)
        self.assertIn("Unexpected production intent decision", workflow)
        self.assertNotIn("gh workflow run storage-incident-management.yml", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
