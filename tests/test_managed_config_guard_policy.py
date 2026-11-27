import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ManagedConfigGuardPolicyTests(unittest.TestCase):
    def test_config_content_stays_protected_while_user_authorizes_metadata_only_sync(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        content = guard["content_protection"]
        metadata = guard["baseline_metadata_policy"]
        expected_paths = {
            "sources/policy.json", "automation/release_manifest.json",
            "automation/production_workflow_map.json", "automation/resource_write_sets.json",
        }
        self.assertEqual(guard["path"], "modules/uu.conf")
        self.assertTrue(guard["content_immutable_to_automation"])
        self.assertTrue(content["owner_may_edit"])
        self.assertTrue(content["owner_manual_edits_allowed"])
        self.assertTrue(content["explicitly_user_authorized_ai_edits_allowed"])
        self.assertTrue(content["ai_edits_require_explicit_user_authorization"])
        self.assertFalse(content["automation_may_modify_content"])
        self.assertFalse(content["production_automation_may_edit_content"])
        self.assertFalse(content["baseline_metadata_registration_may_edit_content"])
        self.assertTrue(metadata["automation_may_read_file"])
        self.assertTrue(metadata["automation_may_identify_file"])
        self.assertTrue(metadata["automation_may_hash_file"])
        self.assertTrue(metadata["automation_may_diff_file"])
        self.assertTrue(metadata["automation_may_update_registered_blob_sha"])
        self.assertTrue(metadata["automation_may_update_release_baseline_sha"])
        self.assertTrue(metadata["automation_may_update_approved_baseline_sha"])
        self.assertTrue(metadata["owner_authored_config_history_required"])
        self.assertTrue(metadata["reviewed_pr_required"])
        self.assertEqual(set(metadata["metadata_write_allowlist"]), expected_paths)
        self.assertTrue(metadata["registration_must_not_write_config_content"])
        self.assertTrue("owner-authored" in metadata["update_authorization"] or "authored by the repository owner" in metadata["update_authorization"])

    def test_observation_remains_read_only_when_owner_history_cannot_be_verified(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        self.assertTrue(guard["content_protection"]["watchdog_near_real_time_reconciliation"])
        reaction = guard["content_protection"]["reaction_model"]
        self.assertIn("RUNNER_TEMP proposal", reaction)
        self.assertTrue("owner-authored" in reaction or "repository-owner-authored" in reaction or "authored by the repository owner" in reaction)
        self.assertIn("Never write config bytes", reaction)


if __name__ == "__main__":
    unittest.main()
