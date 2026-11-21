from __future__ import annotations
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import classify_paths, load_manifest


class ProductionIntentReadOnlyTests(unittest.TestCase):
    def test_production_intent_helpers_do_not_mutate_repository_state_or_call_github_issues(self):
        source = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        self.assertNotIn("--register-ledger", source)
        self.assertNotIn("--merge-observations", source)
        self.assertNotIn("GitHubContentsQueueStore", source)
        self.assertNotIn("/issues/", source)
        self.assertNotIn("gh issue", source)
        for name, end in (
            ("merge_request_observations", "register_unclassified_paths"),
            ("register_unclassified_paths", "main"),
        ):
            helper = source.split(f"def {name}", 1)[1].split(f"def {end}", 1)[0]
            self.assertNotIn("write_text(", helper)
            self.assertNotIn("write_document(", helper)
            self.assertNotIn("subprocess.run", helper)

    def test_unknown_paths_are_reported_and_block_production_until_review(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        classification = classify_paths(["automation/unexpected-control.json"], manifest)
        self.assertEqual(classification["status"], "REVIEW_REQUIRED")
        self.assertEqual(classification["unknown_changes"], ["automation/unexpected-control.json"])
        workflow = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('echo "$intent_json" >> "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn("REVIEW_REQUIRED)", workflow)
        self.assertIn('echo "block_manifest=true" >> "$GITHUB_OUTPUT"', workflow)
        self.assertNotIn("--register-ledger", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
