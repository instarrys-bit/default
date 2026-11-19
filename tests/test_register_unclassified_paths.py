from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionIntentReadOnlyTests(unittest.TestCase):
    def test_production_intent_has_no_repository_mutation_cli(self):
        source = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        self.assertNotIn("--register-ledger", source)
        self.assertNotIn("--merge-observations", source)
        self.assertNotIn("register_unclassified_paths", source)
        self.assertNotIn("merge_request_observations", source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_document(", source)

    def test_watchdog_unknown_path_classification_is_recorded_by_storage_management(self):
        workflow = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("classification=PRODUCTION_INPUT_REVIEW", workflow)
        self.assertIn("gh workflow run storage-incident-management.yml", workflow)
        self.assertNotIn("--register-ledger", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
