import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_automation_write_boundary import validate_write_boundary, BASELINE_ALLOWLIST


class AutomationWriteBoundaryTests(unittest.TestCase):
    def test_current_repository_write_boundary_is_valid(self):
        self.assertEqual(validate_write_boundary(ROOT), [])

    def test_storage_management_declares_the_guarded_metadata_writer(self):
        content = (ROOT / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
        self.assertIn("reconcile-config-baseline:", content)
        self.assertIn("register_config_baseline.py --apply", content)
        self.assertIn("publish_config_baseline_metadata.sh", content)
        self.assertIn("fetch-depth: 0", content)

    def test_baseline_tool_verifies_owner_history_and_config_immutability(self):
        content = (ROOT / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
        self.assertIn("--apply", content)
        self.assertIn("owner_approved_config_history", content)
        self.assertIn("config.read_bytes() != config_bytes", content)
        self.assertIn("ALLOWLIST", content)
        self.assertIn("write_baseline_proposal", content)

    def test_metadata_publisher_has_exact_allowlist_and_stale_main_guard(self):
        content = (ROOT / "scripts/publish_config_baseline_metadata.sh").read_text(encoding="utf-8")
        self.assertIn("git add --", content)
        self.assertIn("git push origin HEAD:main", content)
        self.assertIn("Unexpected modified or untracked paths", content)
        self.assertIn("Unexpected staged paths", content)
        self.assertIn("Protected modules/uu.conf is staged; refusing to commit.", content)
        self.assertNotIn("modules/uu.conf", content.split("allowlist=(", 1)[1].split(")", 1)[0])

    def test_config_drift_is_observed_without_granting_content_write(self):
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
            self.assertEqual(validate_write_boundary(root), [])


if __name__ == "__main__":
    unittest.main()
