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


class ConfigBaselineRegistrationTests(unittest.TestCase):
    def test_owner_history_requires_main_and_verifies_every_config_commit(self):
        commits = ["b" * 40, "a" * 40]
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_REF": "refs/heads/main",
        }, clear=True), patch.object(baseline, "run", side_effect=["c" * 40, "\\n".join(commits), "instarrys-bit", "instarrys-bit"]), patch(
            "register_config_baseline.subprocess.run", return_value=SimpleNamespace(returncode=0)
        ):
            guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "d" * 40}}
            self.assertEqual(baseline.owner_approved_config_history(guard), commits)

    def test_non_owner_commit_keeps_baseline_pending(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_REF": "refs/heads/main",
        }, clear=True), patch.object(baseline, "run", side_effect=["c" * 40, "b" * 40, "someone-else"]), patch(
            "register_config_baseline.subprocess.run", return_value=SimpleNamespace(returncode=0)
        ):
            guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "d" * 40}}
            self.assertEqual(baseline.owner_approved_config_history(guard), [])

    def test_non_main_ref_cannot_advance_baseline(self):
        with patch.dict(os.environ, {
            "GITHUB_REPOSITORY_OWNER": "instarrys-bit",
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_REF": "refs/heads/feature",
        }, clear=True), patch.object(baseline, "run") as mocked:
            guard = {"path": "modules/uu.conf", "last_user_approved_baseline_update": {"commit_sha": "d" * 40}}
            self.assertEqual(baseline.owner_approved_config_history(guard), [])
            mocked.assert_not_called()

    def test_unattributed_change_is_durably_observed_without_config_or_proposal_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sources").mkdir()
            (root / "modules").mkdir()
            (root / "reports").mkdir()
            config = root / "modules" / "uu.conf"
            config.write_bytes(b"[General]\\n# owner-managed\\n")
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
            with patch.object(baseline, "ROOT", root), patch.object(baseline, "owner_approved_config_history", return_value=[]), patch.dict(
                os.environ, {"GITHUB_ACTOR": "someone-else"}, clear=True
            ), patch("sys.argv", ["register_config_baseline.py", "--apply"]):
                self.assertEqual(baseline.main(), 0)
            report = json.loads((root / "reports" / "config-drift-audit.json").read_text(encoding="utf-8"))
            self.assertTrue(report["owner_approved_change_pending_registration"])
            self.assertEqual(report["registered_baseline_git_blob_sha"], "a" * 40)
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse((root / "config-baseline-proposal.json").exists())


if __name__ == "__main__":
    unittest.main()
