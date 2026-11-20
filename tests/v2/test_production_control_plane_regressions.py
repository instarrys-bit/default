from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from production_intent import classify_paths, load_manifest


class ProductionControlPlaneRegressionTests(unittest.TestCase):
    def test_storage_management_changes_do_not_block_ruleset_production(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            ".github/workflows/storage-management.yml",
            "storage/__init__.py",
            "storage/v2/artifact_store.py",
            "storage/v2/artifacts/catalog/43218826799.json",
            "storage/v2/artifacts/sha256/000b92d8f872de41b4bbaa62b92d70c7aca41e75c4c70b23ec0fd789542873f1",
        ]

        result = classify_paths(paths, manifest)

        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertCountEqual(result["non_production_changes"], paths)
        self.assertEqual(result["unknown_changes"], [])

    def test_unregistered_paths_still_require_review(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")

        result = classify_paths(["new/unregistered/control-plane.py"], manifest)

        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["unknown_changes"], ["new/unregistered/control-plane.py"])


class StorageManagementWorkflowRegressionTests(unittest.TestCase):
    def test_incident_store_cli_expands_the_bash_argument_array(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        invocations = [
            line.strip()
            for line in workflow.splitlines()
            if "python3 storage/v2/incident_store.py" in line
        ]

        self.assertEqual(len(invocations), 1)
        self.assertEqual(
            invocations[0],
            'python3 storage/v2/incident_store.py "${args[@]}" | tee "$GITHUB_STEP_SUMMARY"',
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
