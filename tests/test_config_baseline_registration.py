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
from register_config_baseline import (
    apply_baseline_updates, build_release_pin_updates, git_blob_sha, owner_approved_push_changed_config, owner_approved_config_history, write_baseline_proposal,
)


class ConfigBaselineRegistrationTests(unittest.TestCase):
    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_BEFORE": "a" * 40,
        "GITHUB_SHA": "b" * 40,
    }, clear=True)
    def test_owner_push_changing_uu_conf_is_approved(self, mocked):
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
        "GITHUB_SHA": "e" * 40,
    }, clear=True)
    def test_scheduled_run_recovers_only_github_owner_verified_config_history(self, mocked):
        mocked.side_effect = [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=("a" * 40) + "\n" + ("b" * 40) + "\n"),
            SimpleNamespace(returncode=0, stdout="instarrys-bit\n"),
            SimpleNamespace(returncode=0, stdout="instarrys-bit\n"),
        ]
        guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "c" * 40}}
        self.assertEqual(owner_approved_config_history(guard), ["a" * 40, "b" * 40])
        self.assertEqual(mocked.call_count, 4)

    @patch("register_config_baseline.subprocess.run")
    @patch.dict(os.environ, {
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_ACTOR": "instarrys-bit",
        "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
        "GITHUB_REPOSITORY": "instarrys-bit/default",
        "GITHUB_REF": "refs/heads/feature",
        "GITHUB_SHA": "e" * 40,
    }, clear=True)
    def test_scheduled_run_on_non_main_ref_cannot_recover_config_history(self, mocked):
        guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "c" * 40}}
        self.assertEqual(owner_approved_config_history(guard), [])
        mocked.assert_not_called()



    def test_owner_approved_config_proposal_contains_consistent_release_and_inventory_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "automation").mkdir()
            release = {"schema_version": 1, "implementation_pins": {
                "config_baseline": {
                    "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"
                }
            }}
            workflow_map = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            write_sets = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            (root / "automation" / "release_manifest.json").write_text(
                json.dumps(release), encoding="utf-8"
            )
            (root / "automation" / "production_workflow_map.json").write_text(
                json.dumps(workflow_map), encoding="utf-8"
            )
            (root / "automation" / "resource_write_sets.json").write_text(
                json.dumps(write_sets), encoding="utf-8"
            )

            release_text, map_text, write_sets_text = build_release_pin_updates(
                root, "modules/uu.conf", "c" * 40
            )
            release_sha = git_blob_sha(release_text.encode("utf-8"))
            self.assertEqual(
                json.loads(release_text)["implementation_pins"]["config_baseline"]["git_blob_sha"],
                "c" * 40,
            )
            self.assertEqual(
                json.loads(map_text)["review_context"]["release_manifest_blob_sha"], release_sha
            )
            self.assertEqual(
                json.loads(write_sets_text)["review_context"]["release_manifest_blob_sha"], release_sha
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
            for name in ("production_workflow_map.json", "resource_write_sets.json"):
                (root / "automation" / name).write_text(
                    json.dumps({"review_context": {"release_manifest_blob_sha": "b" * 40}}),
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(ValueError, "same read-only owner config path"):
                build_release_pin_updates(root, "modules/uu.conf", "c" * 40)


    def test_baseline_proposal_is_runner_local_and_does_not_touch_repository_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            runner = root / "runner-temp"
            repo.mkdir()
            runner.mkdir()
            protected = repo / "sources" / "policy.json"
            protected.parent.mkdir()
            protected.write_text('{"approved": "old"}', encoding="utf-8")
            before = protected.read_bytes()
            proposal = {"status": "requires_manual_repository_review", "proposed_updates": {"sources/policy.json": {"approved": "new"}}}
            with patch.dict(os.environ, {"RUNNER_TEMP": str(runner)}, clear=True):
                destination = write_baseline_proposal(proposal)
            self.assertEqual(destination.parent, runner)
            self.assertTrue(destination.is_file())
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), proposal)
            self.assertEqual(protected.read_bytes(), before)

    def test_baseline_proposal_rejects_repository_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "runner-temp"
            repo = root / "repo"
            runner.mkdir()
            repo.mkdir()
            with patch.dict(os.environ, {"RUNNER_TEMP": str(runner), "CONFIG_BASELINE_PROPOSAL_PATH": str(repo / "proposal.json")}, clear=True):
                with self.assertRaisesRegex(ValueError, "under RUNNER_TEMP"):
                    write_baseline_proposal({"status": "test"})


    def test_apply_mode_updates_only_baseline_metadata_and_preserves_config_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules").mkdir()
            (root / "modules" / "uu.conf").write_bytes(b"[General]\\n# owner content\\n")
            original = (root / "modules" / "uu.conf").read_bytes()
            sha = git_blob_sha(original)
            (root / "sources").mkdir()
            policy = {"managed_config_guard": {"path": "modules/uu.conf", "approved_git_blob_sha": sha}}
            (root / "automation").mkdir()
            release = {"implementation_pins": {"config_baseline": {
                "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"}}}
            workflow_map = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            write_sets = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            release_text, map_text, sets_text = build_release_pin_updates(root, "modules/uu.conf", sha)
            changed = apply_baseline_updates(root, "modules/uu.conf", sha, policy, release_text, map_text, sets_text)
            self.assertEqual(changed, ["automation/production_workflow_map.json",
                "automation/release_manifest.json", "automation/resource_write_sets.json", "sources/policy.json"])
            self.assertEqual((root / "modules" / "uu.conf").read_bytes(), original)
            self.assertEqual(json.loads((root / "sources" / "policy.json").read_text())["managed_config_guard"]["approved_git_blob_sha"], sha)

    def test_apply_mode_refuses_if_config_sha_changed_after_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules").mkdir()
            (root / "modules" / "uu.conf").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "changed after owner-history verification"):
                apply_baseline_updates(root, "modules/uu.conf", "a" * 40, {}, "{}", "{}", "{}")


if __name__ == "__main__":
    unittest.main()
