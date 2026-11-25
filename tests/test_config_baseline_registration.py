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


class ConfigBaselineProposalTests(unittest.TestCase):
    def test_apply_option_is_not_exposed(self):
        with patch("sys.argv", ["register_config_baseline.py", "--apply"]):
            with self.assertRaises(SystemExit) as caught:
                baseline.main()
        self.assertEqual(caught.exception.code, 2)

    def test_config_change_history_is_read_only_and_not_owner_gated(self):
        head = "a" * 40
        commits = ["b" * 40, "c" * 40]
        mocked = [
            SimpleNamespace(returncode=0, stdout=head, stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="\n".join(commits), stderr=""),
        ]
        with patch.object(baseline.subprocess, "run", side_effect=mocked) as run:
            result = baseline.config_change_history({
                "path": "modules/uu.conf",
                "last_user_approved_baseline_update": {"commit_sha": "d" * 40},
            })
        self.assertEqual(result, commits)
        self.assertTrue(all(call.args[0][0] == "git" for call in run.call_args_list))

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
            proposal = {"status": "requires_reviewed_pr", "repository_files_modified": False}
            with patch.dict(os.environ, {"RUNNER_TEMP": str(runner)}, clear=True):
                destination = baseline.write_baseline_proposal(proposal)
            self.assertEqual(destination.parent, runner)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), proposal)
            self.assertEqual(protected.read_bytes(), before)

    def test_proposal_rejects_repository_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "runner-temp"
            repo = root / "repo"
            runner.mkdir()
            repo.mkdir()
            with patch.dict(os.environ, {
                "RUNNER_TEMP": str(runner),
                "CONFIG_BASELINE_PROPOSAL_PATH": str(repo / "proposal.json"),
            }, clear=True):
                with self.assertRaisesRegex(ValueError, "under RUNNER_TEMP"):
                    baseline.write_baseline_proposal({"status": "test"})

    def test_proposed_release_and_inventory_pins_are_consistent_and_in_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "automation").mkdir()
            release = {
                "schema_version": 1,
                "implementation_pins": {"config_baseline": {
                    "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"
                }},
                "execution_policy": {"watchdog_baseline_metadata_sync": {
                    "writer": "Storage Management", "trigger": ["schedule"], "write_allowlist": ["sources/policy.json"]
                }},
            }
            workflow_map = {"review_context": {"release_manifest_blob_sha": "b" * 40}}
            write_sets = {
                "review_context": {"release_manifest_blob_sha": "b" * 40},
                "policy": {"protected_config": {"metadata_only_sync": {
                    "writer": "Storage Management", "allowed_paths": ["sources/policy.json"]
                }}},
            }
            for name, value in (
                ("release_manifest.json", release),
                ("production_workflow_map.json", workflow_map),
                ("resource_write_sets.json", write_sets),
            ):
                (root / "automation" / name).write_text(json.dumps(value), encoding="utf-8")
            before = {
                path: path.read_bytes()
                for path in (root / "automation" / "release_manifest.json",
                             root / "automation" / "production_workflow_map.json",
                             root / "automation" / "resource_write_sets.json")
            }
            release_text, map_text, sets_text = baseline.build_release_pin_updates(
                root, "modules/uu.conf", "c" * 40
            )
            release_sha = baseline.git_blob_sha(release_text.encode("utf-8"))
            self.assertEqual(json.loads(release_text)["implementation_pins"]["config_baseline"]["git_blob_sha"], "c" * 40)
            self.assertIsNone(json.loads(release_text)["execution_policy"]["watchdog_baseline_metadata_sync"]["writer"])
            self.assertEqual(json.loads(release_text)["execution_policy"]["watchdog_baseline_metadata_sync"]["write_allowlist"], [])
            self.assertEqual(json.loads(map_text)["review_context"]["release_manifest_blob_sha"], release_sha)
            sets = json.loads(sets_text)
            self.assertEqual(sets["review_context"]["release_manifest_blob_sha"], release_sha)
            self.assertIsNone(sets["policy"]["protected_config"]["metadata_only_sync"]["writer"])
            self.assertEqual(sets["policy"]["protected_config"]["metadata_only_sync"]["allowed_paths"], [])
            self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_main_emits_runner_local_proposal_without_repository_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            runner = root / "runner-temp"
            (repo / "sources").mkdir(parents=True)
            (repo / "modules").mkdir()
            (repo / "automation").mkdir()
            runner.mkdir()
            config = repo / "modules" / "uu.conf"
            config.write_bytes(b"[General]\n# user-owned\n")
            actual = baseline.git_blob_sha(config.read_bytes())
            policy = {
                "managed_config_guard": {
                    "path": "modules/uu.conf",
                    "approved_git_blob_sha": "a" * 40,
                    "content_immutable_to_automation": True,
                    "last_user_approved_baseline_update": {"commit_sha": "d" * 40},
                    "baseline_metadata_policy": {},
                }
            }
            policy_path = repo / "sources" / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            (repo / "automation" / "release_manifest.json").write_text(json.dumps({
                "implementation_pins": {"config_baseline": {
                    "path": "modules/uu.conf", "git_blob_sha": "a" * 40, "access": "read_only"
                }},
                "execution_policy": {"watchdog_baseline_metadata_sync": {"writer": "old", "trigger": ["schedule"], "write_allowlist": ["old"]}},
            }), encoding="utf-8")
            (repo / "automation" / "production_workflow_map.json").write_text(json.dumps({
                "review_context": {"release_manifest_blob_sha": "b" * 40}
            }), encoding="utf-8")
            (repo / "automation" / "resource_write_sets.json").write_text(json.dumps({
                "review_context": {"release_manifest_blob_sha": "b" * 40},
                "policy": {"protected_config": {"metadata_only_sync": {"writer": "old", "allowed_paths": ["old"]}}},
            }), encoding="utf-8")
            repo_files = [policy_path, *sorted((repo / "automation").iterdir()), config]
            before = {path: path.read_bytes() for path in repo_files}
            mocked_git = SimpleNamespace(returncode=0, stdout=actual, stderr="")
            with patch.object(baseline, "ROOT", repo), patch.object(baseline, "POLICY", policy_path), patch.object(
                baseline, "CONFIG", config
            ), patch.object(baseline, "config_change_history", return_value=["c" * 40]), patch.object(
                baseline.subprocess, "run", return_value=mocked_git
            ), patch.dict(os.environ, {"RUNNER_TEMP": str(runner), "GITHUB_ACTOR": "test-actor"}, clear=True), patch(
                "sys.argv", ["register_config_baseline.py"]
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(baseline.main(), 0)
            proposal_path = runner / "config-baseline-proposal.json"
            self.assertTrue(proposal_path.is_file())
            proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(proposal["status"], "requires_reviewed_pr")
            self.assertEqual(proposal["new_blob_sha"], actual)
            self.assertFalse(proposal["repository_files_modified"])
            self.assertFalse(proposal["config_file_modified"])
            self.assertEqual({path: path.read_bytes() for path in repo_files}, before)


if __name__ == "__main__":
    unittest.main()
