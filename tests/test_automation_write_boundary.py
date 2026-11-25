import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_automation_write_boundary import validate_write_boundary


class AutomationWriteBoundaryTests(unittest.TestCase):
    def test_current_repository_write_boundary_is_valid(self):
        self.assertEqual(validate_write_boundary(ROOT), [])

    def test_storage_management_has_no_automatic_baseline_writer(self):
        content = (ROOT / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
        self.assertNotIn("reconcile-config-baseline:", content)
        self.assertNotIn("register_config_baseline.py --apply", content)
        self.assertNotIn("publish_config_baseline_metadata.sh", content)

    def test_baseline_tool_is_runner_local_proposal_only(self):
        content = (ROOT / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
        self.assertNotIn("--apply", content)
        self.assertNotIn("owner_approved_config_history", content)
        self.assertIn("RUNNER_TEMP", content)
        self.assertIn("write_baseline_proposal", content)
        self.assertEqual(content.count(".write_text("), 1)
        self.assertIn("destination.write_text(", content)

    def test_retired_publisher_is_fail_closed(self):
        content = (ROOT / "scripts/publish_config_baseline_metadata.sh").read_text(encoding="utf-8")
        self.assertIn("Disabled:", content)
        self.assertNotIn("git add", content)
        self.assertNotIn("git commit", content)
        self.assertNotIn("git push", content)

    def test_production_publisher_has_rulesets_only_fence(self):
        content = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertIn("rulesets/*)", content)
        self.assertIn("Refusing non-ruleset repository write", content)
        self.assertIn("Protected config modules/uu.conf is staged; refusing to commit.", content)

    def test_config_drift_fails_closed_until_reviewed_baseline_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".github/workflows/storage-management.yml",
                ".github/workflows/auto_sync.yml",
                "scripts/register_config_baseline.py",
                "scripts/publish_config_baseline_metadata.sh",
                "sources/policy.json",
                "automation/release_manifest.json",
                "automation/resource_write_sets.json",
                "modules/uu.conf",
            ):
                source = ROOT / relative
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            config = root / "modules" / "uu.conf"
            config.write_bytes(config.read_bytes() + b"\n# observed change\n")
            errors = validate_write_boundary(root)
            self.assertTrue(any("current modules/uu.conf Git blob" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
