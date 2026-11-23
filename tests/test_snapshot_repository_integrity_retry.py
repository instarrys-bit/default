import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "storage" / "v2"))
import snapshot_repository_integrity as snapshot


class SnapshotRepositoryIntegrityRetryTests(unittest.TestCase):
    @patch.object(snapshot.time, "sleep")
    @patch.object(snapshot, "_run_once")
    def test_uu_conf_change_during_snapshot_reacquires_latest_snapshot(self, run_once, _sleep):
        run_once.side_effect = [
            snapshot.IntegritySnapshotError("uu.conf Git blob SHA changed during artifact staging"),
            {"status": "updated", "uu_conf_blob_sha": "c" * 40},
        ]
        result = snapshot.run("instarrys-bit/default", "token")
        self.assertEqual(result["uu_conf_blob_sha"], "c" * 40)
        self.assertEqual(run_once.call_count, 2)

    @patch.object(snapshot.time, "sleep")
    @patch.object(snapshot, "_run_once")
    def test_retry_budget_is_bounded_for_repeated_config_changes(self, run_once, _sleep):
        run_once.side_effect = snapshot.IntegritySnapshotError("uu.conf changed during snapshot")
        with self.assertRaises(snapshot.IntegritySnapshotError):
            snapshot.run("instarrys-bit/default", "token")
        self.assertEqual(run_once.call_count, snapshot.MAX_SNAPSHOT_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
