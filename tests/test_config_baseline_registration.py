import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from types import SimpleNamespace
from register_config_baseline import (\n    build_release_pin_updates, git_blob_sha, owner_approved_push_changed_config, owner_approved_config_history,\n)


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



    def test_owner_approved_config_registration_updates_release_and_workflow_map_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "automation").mkdir()
            release = {
                "schema_version": 1,
                "implementation_pins": {
                    "config_baseline": {
                        "path": "modules/uu.conf",
                        "git_blob_sha": "a" * 40,
                        "access": "read_only",
                    }
                },
            }
            workflow_map = {
                "review_context": {"release_manifest_blob_sha": "b" * 40}
            }
            (root / "automation" / "release_manifest.json").write_text(
                json.dumps(release), encoding="utf-8"
            )
            (root / "automation" / "production_workflow_map.json").write_text(
                json.dumps(workflow_map), encoding="utf-8"
            )

            release_text, workflow_map_text = build_release_pin_updates(
                root, "modules/uu.conf", "c" * 40
            )
            updated_release = json.loads(release_text)
            updated_map = json.loads(workflow_map_text)
            self.assertEqual(
                updated_release["implementation_pins"]["config_baseline"]["git_blob_sha"],
                "c" * 40,
            )
            self.assertEqual(
                updated_release["implementation_pins"]["config_baseline"]["access"],
                "read_only",
            )
            self.assertEqual(
                updated_map["review_context"]["release_manifest_blob_sha"],
                git_blob_sha(release_text.encode("utf-8")),
            )

    def test_release_pin_update_rejects_non_owner_config_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "automation").mkdir()
            (root / "automation" / "release_manifest.json").write_text(
                json.dumps({"implementation_pins": {"config_baseline": {
                    "path": "shadowrocket/ss.conf", "git_blob_sha": "a" * 40,
                    "access": "read_only",
                }}}),
                encoding="utf-8",
            )
            (root / "automation" / "production_workflow_map.json").write_text(
                json.dumps({"review_context": {"release_manifest_blob_sha": "b" * 40}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "same read-only owner config path"):
                build_release_pin_updates(root, "modules/uu.conf", "c" * 40)

if __name__ == "__main__":
    unittest.main()
