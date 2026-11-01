import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from register_config_baseline import owner_approved_push_changed_config


class ConfigBaselineRegistrationTests(unittest.TestCase):
    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_BEFORE": "a" * 40,
        "GITHUB_SHA": "b" * 40,
    }, clear=True)
    def test_owner_push_changing_ss_conf_is_approved(self, mocked):
        mocked.return_value.stdout = "shadowrocket/ss.conf\n"
        self.assertTrue(owner_approved_push_changed_config())

    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "other-user",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_BEFORE": "a" * 40,
        "GITHUB_SHA": "b" * 40,
    }, clear=True)
    def test_non_owner_push_is_not_approved(self, mocked):
        self.assertFalse(owner_approved_push_changed_config())
        mocked.assert_not_called()

    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_BEFORE": "a" * 40,
        "GITHUB_SHA": "b" * 40,
    }, clear=True)
    def test_scheduled_run_cannot_approve_config_change(self, mocked):
        self.assertFalse(owner_approved_push_changed_config())
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
