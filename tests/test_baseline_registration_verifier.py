import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_baseline import validate_registration_metadata


class BaselineRegistrationVerifierTests(unittest.TestCase):
    def setUp(self):
        self.base = {"approved_git_blob_sha": "a" * 40}
        self.head = {
            "approved_git_blob_sha": "b" * 40,
            "last_user_approved_baseline_update": {
                "previous_blob_sha": "a" * 40,
                "new_blob_sha": "b" * 40,
                "approval_mode": "user_authorized_automatic_sha_follow",
                "actor": "github-actions[bot]",
                "config_change_commits": ["2" * 40, "3" * 40],
                "commit_sha": "2" * 40,
                "registered_at": "2026-11-23T14:00:00Z",
            },
        }
        self.commits = ["2" * 40, "3" * 40]

    def test_accepts_user_authorized_registration_from_non_owner_actor(self):
        validate_registration_metadata(self.base, self.head, "b" * 40, self.commits)

    def test_rejects_wrong_current_blob(self):
        with self.assertRaisesRegex(ValueError, "current uu.conf"):
            validate_registration_metadata(self.base, self.head, "c" * 40, self.commits)

    def test_rejects_incomplete_commit_inventory(self):
        with self.assertRaisesRegex(ValueError, "every intervening"):
            validate_registration_metadata(self.base, self.head, "b" * 40, self.commits[:1])

    def test_rejects_unapproved_mode(self):
        self.head["last_user_approved_baseline_update"]["approval_mode"] = "manual"
        with self.assertRaisesRegex(ValueError, "user-authorized automatic SHA-follow"):
            validate_registration_metadata(self.base, self.head, "b" * 40, self.commits)

    def test_requires_actor_evidence_without_requiring_owner_identity(self):
        self.head["last_user_approved_baseline_update"]["actor"] = ""
        with self.assertRaisesRegex(ValueError, "actor evidence"):
            validate_registration_metadata(self.base, self.head, "b" * 40, self.commits)


if __name__ == "__main__":
    unittest.main()
