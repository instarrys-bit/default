import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_baseline import owner_approved_push_changed_config


POLICY = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
ANCHOR = POLICY["managed_config_guard"]["last_user_approved_baseline_update"]["commit_sha"]


class VerifyBaselineOwnerHistoryTests(unittest.TestCase):
    @patch("verify_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_ACTOR": "github-actions[bot]",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_SHA": "d" * 40,
        "GH_TOKEN": "test-token",
    }, clear=True)
    def test_historical_owner_config_commits_are_verified_with_one_api_call(self, mocked):
        first, second = "b" * 40, "a" * 40
        payload = [
            {"sha": first, "author": {"login": "instarrys-bit"}},
            {"sha": second, "author": {"login": "instarrys-bit"}},
            {"sha": ANCHOR, "author": {"login": "instarrys-bit"}},
        ]
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=first + "\n" + second + "\n"),
            SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
        ]
        self.assertTrue(owner_approved_push_changed_config())
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(mocked.call_args_list[-1].args[0][0:2], ["gh", "api"])

    @patch("verify_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_SHA": "d" * 40,
        "GH_TOKEN": "test-token",
    }, clear=True)
    def test_any_non_owner_config_commit_keeps_baseline_check_fail_closed(self, mocked):
        first = "b" * 40
        payload = [
            {"sha": first, "author": {"login": "someone-else"}},
            {"sha": ANCHOR, "author": {"login": "instarrys-bit"}},
        ]
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=first + "\n"),
            SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
        ]
        self.assertFalse(owner_approved_push_changed_config())

    @patch("verify_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/feature",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_SHA": "d" * 40,
    }, clear=True)
    def test_non_main_push_cannot_bypass_the_registered_baseline(self, mocked):
        self.assertFalse(owner_approved_push_changed_config())
        mocked.assert_not_called()

    @patch("verify_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_SHA": "d" * 40,
    }, clear=True)
    def test_missing_approved_anchor_in_api_page_fails_closed(self, mocked):
        first = "b" * 40
        payload = [{"sha": first, "author": {"login": "instarrys-bit"}}]
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=f"{first}\\n"),
            SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
        ]
        self.assertFalse(owner_approved_push_changed_config())


if __name__ == "__main__":
    unittest.main()
