import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ManagedConfigGuardPolicyTests(unittest.TestCase):
    def test_config_content_is_protected_while_baseline_metadata_remains_trackable(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        content = guard["content_protection"]
        metadata = guard["baseline_metadata_policy"]

        self.assertEqual(guard["path"], "modules/uu.conf")
        self.assertTrue(guard["content_immutable_to_automation"])
        self.assertTrue(content["owner_may_edit"])
        self.assertFalse(content["automation_may_modify_content"])
        self.assertIn("user-authored rules", content["protected_scope"])
        self.assertTrue(metadata["automation_may_read_file"])
        self.assertTrue(metadata["automation_may_identify_file"])
        self.assertTrue(metadata["automation_may_hash_file"])
        self.assertTrue(metadata["automation_may_diff_file"])
        self.assertTrue(metadata["automation_may_update_registered_blob_sha"])
        self.assertTrue(metadata["registration_must_not_write_config_content"])
        self.assertIn("Owner-verified registration only", metadata["update_authorization"])

    def test_old_ambiguous_immutable_field_is_not_used(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        self.assertNotIn("immutable", policy["managed_config_guard"])


if __name__ == "__main__":
    unittest.main()
