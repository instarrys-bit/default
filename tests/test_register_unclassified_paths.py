from __future__ import annotations
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import classify_paths, load_manifest


class ProductionIntentReadOnlyTests(unittest.TestCase):
    def test_production_intent_has_no_repository_mutation_cli(self):
        source = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        self.assertNotIn("--register-ledger", source)
        self.assertNotIn("--merge-observations", source)
        self.assertNotIn("merge_request_observations", source)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_document(", source)
        helper = source.split("def register_unclassified_paths", 1)[1].split("def main", 1)[0]
        self.assertNotIn("write_text(", helper)
        self.assertNotIn("subprocess.run", helper)
        self.assertNotIn("GitHubContentsQueueStore", helper)

    def test_watchdog_unknown_path_classification_is_recorded_by_storage_management(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        classification = classify_paths(["automation/unexpected-control.json"], manifest)
        self.assertEqual(classification["status"], "REVIEW_REQUIRED")
        self.assertEqual(classification["unknown_changes"], ["automation/unexpected-control.json"])

        workflow = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('echo "$intent_json" | tee -a "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn('if [ "$decision" = "REVIEW_REQUIRED" ]; then', workflow)
        self.assertIn('echo "block_manifest=true" >> "$GITHUB_OUTPUT"', workflow)
        self.assertNotIn("storage-incident-management.yml", workflow)
        self.assertNotIn("--register-ledger", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
