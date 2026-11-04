import json
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

    def test_audit_hook_rejects_protected_config_open(self):
        with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
            fenced_file_writer._audit_hook("open", (ROOT / "shadowrocket" / "ss.conf", "w", os.O_WRONLY))

    def test_audit_hook_checks_repo_local_open_before_write(self):
        target = ROOT / "sources" / "test-only.json"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer._audit_hook("open", (target, "w", os.O_WRONLY | os.O_CREAT))
                check.assert_called_once_with("sources/test-only.json")

    def test_audit_hook_denies_descriptor_based_mutation(self):
        with self.assertRaisesRegex(PermissionError, "descriptor-based filesystem mutations"):
            fenced_file_writer._audit_hook("os.utime", (7, None, None))

    def test_every_registered_python_component_installs_the_guard(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        components = [item for item in registry["programs"] if item.get("kind") == "python_component"]
        self.assertEqual(len(components), 53)
        missing = []
        for item in components:
            path = ROOT / item["path"]
            source = path.read_text(encoding="utf-8")
            if item["id"] == "script_fenced_file_writer":
                if "def install_write_guard" not in source:
                    missing.append(item["path"])
            elif "_install_write_guard" not in source:
                missing.append(item["path"])
        self.assertEqual(missing, [], f"Python components missing write guard: {missing}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
