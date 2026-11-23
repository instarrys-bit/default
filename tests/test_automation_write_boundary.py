import shutil
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

    def test_owner_config_drift_is_observed_without_breaking_read_only_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                ".github/workflows/storage-management.yml",
                ".github/workflows/auto_sync.yml",
                "scripts/register_config_baseline.py",
                "sources/policy.json",
                "automation/release_manifest.json",
                "automation/resource_write_sets.json",
                "modules/uu.conf",
            ):
                source = ROOT / relative
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            config = root / "modules" / "uu.conf"
            config.write_bytes(config.read_bytes() + b"\\n# owner-approved change\\n")
            self.assertEqual(validate_write_boundary(root), [])

    def test_storage_management_has_no_baseline_writer(self):
        content = (ROOT / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
        self.assertNotIn("reconcile-config-baseline:", content)
        self.assertNotIn("register_config_baseline.py --apply", content)

    def test_production_publisher_has_rulesets_only_fence(self):
        content = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertIn("rulesets/*)", content)
        self.assertIn("Refusing non-ruleset repository write", content)
        self.assertIn("Protected config modules/uu.conf is staged; refusing to commit.", content)

    def test_baseline_tool_is_proposal_only(self):
        content = (ROOT / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
        self.assertNotIn("--apply", content)
        self.assertNotIn("def apply_baseline_updates(", content)


if __name__ == "__main__":
    unittest.main()
