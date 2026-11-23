import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_baseline


class VerifyBaselineTests(unittest.TestCase):
    def test_unregistered_uu_conf_sha_is_observed_without_blocking_read_only_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules").mkdir()
            config = root / "modules" / "uu.conf"
            config.write_text("[General]\\n", encoding="utf-8")
            policy = root / "policy.json"
            policy.write_text(json.dumps({"managed_config_guard": {
                "path": "modules/uu.conf", "approved_git_blob_sha": "a" * 40
            }}), encoding="utf-8")
            with patch.object(verify_baseline, "ROOT", root), patch.object(verify_baseline, "POLICY", policy), patch(
                "sys.argv", ["verify_baseline.py"]
            ):
                self.assertEqual(verify_baseline.main(), 0)

    def test_registered_config_sha_passes_read_only_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "modules").mkdir()
            config = root / "modules" / "uu.conf"
            data = b"[General]\\n"
            config.write_bytes(data)
            policy = root / "policy.json"
            policy.write_text(json.dumps({"managed_config_guard": {
                "path": "modules/uu.conf", "approved_git_blob_sha": verify_baseline.git_blob_sha(data)
            }}), encoding="utf-8")
            with patch.object(verify_baseline, "ROOT", root), patch.object(verify_baseline, "POLICY", policy), patch(
                "sys.argv", ["verify_baseline.py"]
            ):
                self.assertEqual(verify_baseline.main(), 0)


if __name__ == "__main__":
    unittest.main()
