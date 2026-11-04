import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fenced_file_writer


class FencedFileWriterTests(unittest.TestCase):
    def test_owner_managed_config_is_always_read_only(self):
        with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
            fenced_file_writer.authorize_write_path(ROOT / "shadowrocket" / "ss.conf")

    def test_repo_local_write_requires_live_lease_in_production_mode(self):
        target = ROOT / "sources" / "review_cursor.json"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer.authorize_write_path(target)
                check.assert_called_once_with("sources/review_cursor.json")

    def test_non_repository_temporary_files_are_not_subject_to_repository_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
                with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                    fenced_file_writer.authorize_write_path(Path(directory) / "external.tmp")
                    check.assert_not_called()

    def test_local_unit_test_writes_do_not_require_a_production_lease(self):
        target = ROOT / "sources" / "review_cursor.json"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "0"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer.authorize_write_path(target)
                check.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
