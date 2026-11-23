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
        self.assertTrue(content["owner_manual_edits_allowed"])
        self.assertTrue(content["explicitly_user_authorized_ai_edits_allowed"])
        self.assertTrue(content["ai_edits_require_explicit_user_authorization"])
        self.assertTrue(content["user_may_edit_content"])
        self.assertTrue(content["user_authorized_ai_may_edit_content"])
        self.assertFalse(content["production_automation_may_edit_content"])
        self.assertFalse(content["baseline_metadata_registration_may_edit_content"])
        self.assertIn("user explicitly authorizes a specific content change", content["protected_scope"])
        self.assertFalse(content["automation_may_modify_content"])
        self.assertIn("user-authored rules", content["protected_scope"])
        self.assertTrue(metadata["automation_may_read_file"])
        self.assertTrue(metadata["automation_may_identify_file"])
        self.assertTrue(metadata["automation_may_hash_file"])
        self.assertTrue(metadata["automation_may_diff_file"])
        self.assertTrue(metadata["automation_may_update_registered_blob_sha"])
        self.assertTrue(metadata["registration_must_not_write_config_content"])
        self.assertIn("File Management is the sole authorized writer", metadata["update_authorization"])
        self.assertIn("Production automation, Watchdog and ruleset publishers cannot update baseline metadata", metadata["update_authorization"])

    def test_config_change_policy_requires_follow_through_without_auto_approval(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        content = guard["content_protection"]
        metadata = guard["baseline_metadata_policy"]

        self.assertTrue(content["watchdog_near_real_time_reconciliation"])
        self.assertIn("record the observed Git blob SHA", content["reaction_model"])
        self.assertIn("reacquire the latest main-branch file", content["reaction_model"])
        self.assertIn("continue read-only audit and scheduling", content["reaction_model"])
        self.assertIn("independently of owner-attribution status", metadata["update_authorization"])
        self.assertIn("must never write config content", metadata["update_authorization"])

    def test_old_ambiguous_immutable_field_is_not_used(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        self.assertNotIn("immutable", policy["managed_config_guard"])


if __name__ == "__main__":
    unittest.main()
