import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import register_config_baseline as baseline


class ConfigBaselineRegistrationTests(unittest.TestCase):
    def test_any_commit_author_is_recorded_but_never_blocks_sha_follow(self):
        commits = ["b" * 40, "a" * 40]
        with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main"}, clear=True), patch.object(
            baseline, "run", side_effect=["c" * 40, "\n".join(commits)]
        ), patch("register_config_baseline.subprocess.run", return_value=type("R", (), {"returncode": 0})()):
            guard = {"last_user_approved_baseline_update": {"commit_sha": "d" * 40}}
            self.assertEqual(baseline.config_change_history(guard), commits)

    def test_non_main_ref_cannot_advance_baseline(self):
        with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/feature"}, clear=True), patch.object(
            baseline, "run"
        ) as mocked:
            self.assertEqual(baseline.config_change_history({}), [])
            mocked.assert_not_called()

    def test_missing_or_non_ancestor_anchor_still_tracks_latest_config_commit(self):
        with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main"}, clear=True), patch.object(
            baseline, "run", side_effect=["c" * 40, "e" * 40]
        ), patch("register_config_baseline.subprocess.run", return_value=type("R", (), {"returncode": 1})()):
            self.assertEqual(baseline.config_change_history({"last_user_approved_baseline_update": {"commit_sha": "d" * 40}}), ["e" * 40])


    def test_non_main_ref_never_advances_approved_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sources").mkdir()
            (root / "modules").mkdir()
            config = root / "modules" / "uu.conf"
            config.write_bytes(b"[General]\\n")
            policy = {
                "managed_config_guard": {
                    "path": "modules/uu.conf",
                    "approved_git_blob_sha": "a" * 40,
                    "content_immutable_to_automation": True,
                },
                "dns_invariants": {},
            }
            policy_path = root / "sources" / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with patch.object(baseline, "ROOT", root), patch.dict(os.environ, {"GITHUB_REF": "refs/heads/feature"}, clear=True), patch(
                "sys.argv", ["register_config_baseline.py", "--apply"]
            ):
                self.assertEqual(baseline.main(), 0)
            after = json.loads(policy_path.read_text(encoding="utf-8"))
            self.assertEqual(after["managed_config_guard"]["approved_git_blob_sha"], "a" * 40)

    def test_unattributed_change_is_automatically_registered_without_config_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sources").mkdir()
            (root / "modules").mkdir()
            (root / "reports").mkdir()
            config = root / "modules" / "uu.conf"
            config.write_bytes(b"[General]\n# user-managed\n")
            original = config.read_bytes()
            policy = {
                "managed_config_guard": {
                    "path": "modules/uu.conf",
                    "approved_git_blob_sha": "a" * 40,
                    "content_immutable_to_automation": True,
                    "last_user_approved_baseline_update": {"commit_sha": "b" * 40},
                },
                "dns_invariants": {},
            }
            (root / "sources" / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
            (root / "reports" / "config-drift-audit.json").write_text("{}", encoding="utf-8")
            with patch.object(baseline, "ROOT", root), patch.object(baseline, "config_change_history", return_value=["c" * 40]), patch.object(
                baseline, "prepare_metadata", return_value={"sources/policy.json": json.dumps(policy)}
            ), patch.object(baseline, "run", return_value=""), patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main", "GITHUB_ACTOR": "some-contributor"}, clear=True), patch(
                "sys.argv", ["register_config_baseline.py", "--apply"]
            ):
                self.assertEqual(baseline.main(), 0)
            self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
