import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import register_config_baseline as baseline


class ConfigBaselineMetadataTests(unittest.TestCase):
    def test_apply_option_is_exposed_for_guarded_storage_management_use(self):
        content = (ROOT / "scripts" / "register_config_baseline.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--apply"', content)
        self.assertIn("Storage Management main push/schedule job", content)

    def test_config_change_history_requires_owner_authored_commits(self):
        head = "a" * 40
        commits = ["b" * 40, "c" * 40]
        with patch.object(baseline, "run", side_effect=[head, "\n".join(commits), "instarrys-bit", "instarrys-bit"]) as run, patch.object(
            baseline.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")
        ), patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_REF": "refs/heads/main",
        }, clear=True):
            result = baseline.owner_approved_config_history({
                "path": "modules/uu.conf",
                "last_user_approved_baseline_update": {"commit_sha": "d" * 40},
            })
        self.assertEqual(result, commits)
        self.assertEqual(run.call_count, 4)
        self.assertTrue(all(call.args[0][0] in {"git", "gh"} for call in run.call_args_list))

    def test_config_change_history_holds_non_owner_commit(self):
        with patch.object(baseline, "run", side_effect=["a" * 40, "b" * 40, "someone-else"]) as run, patch.object(
            baseline.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")
        ), patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_REF": "refs/heads/main",
        }, clear=True):
            result = baseline.owner_approved_config_history({
                "path": "modules/uu.conf",
                "last_user_approved_baseline_update": {"commit_sha": "d" * 40},
            })
        self.assertEqual(result, [])

    def test_proposal_is_written_only_under_runner_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            runner = root / "runner-temp"
            repo.mkdir()
            runner.mkdir()
            protected = repo / "sources" / "policy.json"
            protected.parent.mkdir()
            protected.write_text('{"approved":"old"}', encoding="utf-8")
            before = protected.read_bytes()
            proposal = {"status": "observed_pending_owner_attribution", "repository_files_modified": False}
            with patch.dict(os.environ, {"RUNNER_TEMP": str(runner)}, clear=True):
                destination = baseline.write_baseline_proposal(proposal)
            self.assertEqual(destination.parent, runner)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), proposal)
            self.assertEqual(protected.read_bytes(), before)

    def test_proposal_rejects_repository_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner, repo = root / "runner-temp", root / "repo"
            runner.mkdir()
            repo.mkdir()
            with patch.dict(os.environ, {
                "RUNNER_TEMP": str(runner),
                "CONFIG_BASELINE_PROPOSAL_PATH": str(repo / "proposal.json"),
            }, clear=True):
                with self.assertRaisesRegex(ValueError, "under RUNNER_TEMP"):
                    baseline.write_baseline_proposal({"status": "test"})

    def test_release_and_inventory_metadata_allowlists_are_consistent_and_in_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "automation").mkdir()
            release = {
                "schema_version": 1,
                "implementation_pins": {"config_baseline": {
                    "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"
                }},
                "execution_policy": {"watchdog_baseline_metadata_sync": {
                    "writer": None, "trigger": [], "write_allowlist": []
                }},
            }
            workflow_map = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            write_sets = {
                "review_context": {"release_manifest_blob_sha": "b" * 40},
                "policy": {"protected_config": {"metadata_only_sync": {
                    "writer": None, "allowed_paths": [], "never_write": ["modules/uu.conf"]
                }}},
            }
            for name, value in (
                ("release_manifest.json", release),
                ("production_workflow_map.json", workflow_map),
                ("resource_write_sets.json", write_sets),
            ):
                (root / "automation" / name).write_text(json.dumps(value), encoding="utf-8")
            before = {path: path.read_bytes() for path in (root / "automation").iterdir()}
            release_text, map_text, sets_text = baseline.build_release_pin_updates(root, "modules/uu.conf", "c" * 40)
            release_sha = baseline.git_blob_sha(release_text.encode("utf-8"))
            release_doc = json.loads(release_text)
            self.assertEqual(release_doc["implementation_pins"]["config_baseline"]["git_blob_sha"], "c" * 40)
            sync = release_doc["execution_policy"]["watchdog_baseline_metadata_sync"]
            self.assertEqual(sync["writer"], baseline.WRITER)
            self.assertEqual(set(sync["write_allowlist"]), set(baseline.ALLOWLIST))
            self.assertEqual(json.loads(map_text)["review_context"]["release_manifest_blob_sha"], release_sha)
            sets = json.loads(sets_text)
            self.assertEqual(sets["review_context"]["release_manifest_blob_sha"], release_sha)
            self.assertEqual(sets["policy"]["protected_config"]["metadata_only_sync"]["writer"], baseline.WRITER)
            self.assertEqual(set(sets["policy"]["protected_config"]["metadata_only_sync"]["allowed_paths"]), set(baseline.ALLOWLIST))
            self.assertEqual(sets["policy"]["protected_config"]["metadata_only_sync"]["never_write"], ["modules/uu.conf"])
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def _make_repo(self, root: Path):
        (root / "sources").mkdir()
        (root / "modules").mkdir()
        (root / "automation").mkdir()
        config = root / "modules" / "uu.conf"
        config.write_bytes(b"[General]\n# user-owned\n")
        actual = baseline.git_blob_sha(config.read_bytes())
        policy = {"managed_config_guard": {
            "path": "modules/uu.conf", "approved_git_blob_sha": "a" * 40,
            "content_immutable_to_automation": True,
            "last_user_approved_baseline_update": {"commit_sha": "d" * 40},
            "baseline_metadata_policy": {},
            "content_protection": {"automation_may_modify_content": False},
        }}
        policy_path = root / "sources" / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        (root / "automation" / "release_manifest.json").write_text(json.dumps({
            "implementation_pins": {"config_baseline": {
                "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"
            }},
            "execution_policy": {"watchdog_baseline_metadata_sync": {
                "writer": None, "trigger": [], "write_allowlist": []
            }},
        }), encoding="utf-8")
        (root / "automation" / "production_workflow_map.json").write_text(json.dumps({
            "review_context": {"release_manifest_blob_sha": "b" * 40}
        }), encoding="utf-8")
        (root / "automation" / "resource_write_sets.json").write_text(json.dumps({
            "review_context": {"release_manifest_blob_sha": "b" * 40},
            "policy": {"protected_config": {"metadata_only_sync": {
                "writer": None, "allowed_paths": [], "never_write": ["modules/uu.conf"]
            }}},
        }), encoding="utf-8")
        return config, policy_path, actual

    def test_main_emits_runner_local_proposal_without_repository_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, runner = root / "repo", root / "runner-temp"
            repo.mkdir()
            runner.mkdir()
            config, policy_path, actual = self._make_repo(repo)
            repo_files = [policy_path, *sorted((repo / "automation").iterdir()), config]
            before = {path: path.read_bytes() for path in repo_files}
            with patch.object(baseline, "ROOT", repo), patch.object(baseline, "POLICY", policy_path), patch.object(
                baseline, "CONFIG", config
            ), patch.object(baseline, "owner_approved_config_history", return_value=["c" * 40]), patch.object(
                baseline, "run", return_value=actual
            ), patch.dict(os.environ, {
                "RUNNER_TEMP": str(runner), "GITHUB_ACTOR": "instarrys-bit",
                "GITHUB_REPOSITORY_OWNER": "instarrys-bit", "GITHUB_REPOSITORY": "instarrys-bit/default",
            }, clear=True), patch("sys.argv", ["register_config_baseline.py"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(baseline.main(), 0)
            proposal_path = runner / "config-baseline-proposal.json"
            self.assertTrue(proposal_path.is_file())
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(proposal["status"], "owner_history_verified_metadata_update_ready")
            self.assertEqual(proposal["new_blob_sha"], actual)
            self.assertEqual(set(proposal["proposed_updates"]), set(baseline.ALLOWLIST))
            self.assertFalse(proposal["repository_files_modified"])
            self.assertFalse(proposal["config_file_modified"])
            self.assertEqual({path: path.read_bytes() for path in repo_files}, before)

    def test_apply_updates_only_metadata_allowlist_and_never_config_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            config, policy_path, actual = self._make_repo(repo)
            repo_files = [policy_path, *sorted((repo / "automation").iterdir()), config]
            before = {path: path.read_bytes() for path in repo_files}
            before_config = config.read_bytes()
            with patch.object(baseline, "ROOT", repo), patch.object(baseline, "POLICY", policy_path), patch.object(
                baseline, "CONFIG", config
            ), patch.object(baseline, "owner_approved_config_history", return_value=["c" * 40]), patch.object(
                baseline, "run", side_effect=[actual, "", "\n".join(baseline.ALLOWLIST)]
            ), patch.dict(os.environ, {
                "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main",
                "GITHUB_REPOSITORY_OWNER": "instarrys-bit", "GITHUB_REPOSITORY": "instarrys-bit/default",
                "GITHUB_ACTOR": "instarrys-bit",
            }, clear=True), patch("sys.argv", ["register_config_baseline.py", "--apply"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(baseline.main(), 0)
            self.assertEqual(config.read_bytes(), before_config)
            changed = {path.relative_to(repo).as_posix() for path in repo_files if path.read_bytes() != before[path]}
            self.assertEqual(changed, set(baseline.ALLOWLIST))
            updated_policy = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_policy["managed_config_guard"]["approved_git_blob_sha"], actual)
            self.assertTrue(updated_policy["managed_config_guard"]["baseline_metadata_policy"]["automation_may_update_approved_baseline_sha"])
            self.assertFalse(updated_policy["managed_config_guard"]["content_protection"]["automation_may_modify_content"])


if __name__ == "__main__":
    unittest.main()
