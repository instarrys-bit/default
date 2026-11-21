import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_automation_write_boundary import validate_write_boundary


class AutomationWriteBoundaryTests(unittest.TestCase):
    def test_current_repository_write_boundary_is_valid(self):
        self.assertEqual(validate_write_boundary(ROOT), [])

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
