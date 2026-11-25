import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ManagedConfigGuardPolicyTests(unittest.TestCase):
    def test_config_content_is_protected_and_baseline_metadata_requires_reviewed_pr(self):
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
        self.assertFalse(content["automation_may_modify_content"])
        self.assertFalse(content["production_automation_may_edit_content"])
        self.assertFalse(content["baseline_metadata_registration_may_edit_content"])
        self.assertTrue(metadata["automation_may_read_file"])
        self.assertTrue(metadata["automation_may_identify_file"])
        self.assertTrue(metadata["automation_may_hash_file"])
        self.assertTrue(metadata["automation_may_diff_file"])
        self.assertFalse(metadata["automation_may_update_registered_blob_sha"])
        self.assertFalse(metadata["automation_may_update_release_baseline_sha"])
        self.assertFalse(metadata["automation_may_update_approved_baseline_sha"])
        self.assertTrue(metadata["reviewed_pr_required"])
        self.assertEqual(metadata["proposal_generation_mode"], "runner_local_only")
        self.assertIn("separately reviewed pull request", metadata["update_authorization"])

    def test_observation_is_read_only_and_never_automatically_advances_baseline(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        self.assertTrue(guard["content_protection"]["watchdog_near_real_time_reconciliation"])
        self.assertIn("runner-local proposal", guard["content_protection"]["reaction_model"])
        self.assertIn("separate reviewed pull request", guard["content_protection"]["reaction_model"])
        self.assertNotIn("automatically update the registered baseline", guard["content_protection"]["reaction_model"])


if __name__ == "__main__":
    unittest.main()
