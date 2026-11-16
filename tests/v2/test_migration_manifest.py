import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from migration import validate_migration_manifest


class V1MigrationManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "storage/v2/migration/v1-source-manifest.json").read_text(encoding="utf-8"))
        self.inventory = json.loads((ROOT / "docs/v2/legacy-v1-inventory.json").read_text(encoding="utf-8"))

    def test_manifest_covers_allowlisted_v1_data_without_importing_it(self):
        result = validate_migration_manifest(self.manifest, self.inventory)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 66)
        self.assertFalse(result["legacy_queue_imported"])

    def test_user_configuration_is_reference_only_and_manual_edits_are_allowed(self):
        result = validate_migration_manifest(self.manifest, self.inventory)
        self.assertTrue(result["user_config_manual_edits_allowed"])
        self.assertEqual(self.manifest["user_configuration_reference"]["automation_access"], "READ_ONLY")
        self.assertEqual(self.manifest["user_configuration_reference"]["manual_user_access"], "ALLOWED")

    def test_rejects_uninventoried_source(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["entries"][0]["source_path"] = "modules/uu.conf"
        with self.assertRaisesRegex(ValueError, "not in the V1 allowlisted inventory"):
            validate_migration_manifest(broken, self.inventory)

    def test_rejects_legacy_queue_state_import(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["policy"]["legacy_active_leases_imported"] = True
        with self.assertRaisesRegex(ValueError, "legacy_active_leases_imported"):
            validate_migration_manifest(broken, self.inventory)

    def test_rejects_promoting_unverified_data(self):
        broken = json.loads(json.dumps(self.manifest))
        broken["entries"][0]["promotion_status"] = "ACCEPTED"
        with self.assertRaisesRegex(ValueError, "remain quarantined"):
            validate_migration_manifest(broken, self.inventory)


if __name__ == "__main__":
    unittest.main()
