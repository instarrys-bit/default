import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from types import SimpleNamespace
from register_config_baseline import owner_approved_push_changed_config, owner_approved_config_history


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
        mocked.return_value.stdout = "modules/uu.conf\n"
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


    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_BEFORE": "d" * 40,
        "GITHUB_SHA": "e" * 40,
    }, clear=True)
    def test_recovers_interrupted_registration_from_owner_verified_config_history(self, mocked):
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=("a" * 40) + "\n" + ("b" * 40) + "\n"),
            SimpleNamespace(returncode=0, stdout="instarrys-bit\n"),
            SimpleNamespace(returncode=0, stdout="instarrys-bit\n"),
        ]
        guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "c" * 40}}
        self.assertEqual(owner_approved_config_history(guard), ["a" * 40, "b" * 40])

    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_BEFORE": "d" * 40,
        "GITHUB_SHA": "e" * 40,
    }, clear=True)
    def test_rejects_history_containing_non_owner_config_commit(self, mocked):
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=("a" * 40) + "\n"),
            SimpleNamespace(returncode=0, stdout="someone-else\n"),
        ]
        guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "c" * 40}}
        self.assertEqual(owner_approved_config_history(guard), [])

    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_BEFORE": "d" * 40,
        "GITHUB_SHA": "e" * 40,
    }, clear=True)
    def test_scheduled_run_cannot_recover_config_history(self, mocked):
        guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "c" * 40}}
        self.assertEqual(owner_approved_config_history(guard), [])
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
