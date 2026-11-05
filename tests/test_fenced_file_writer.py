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
    def test_uu_conf_is_always_read_only(self):
        with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
            fenced_file_writer.authorize_write_path(ROOT / "modules" / "uu.conf")

    def test_uu_conf_open_is_rejected_by_audit_hook(self):
        with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
            fenced_file_writer._audit_hook("open", (ROOT / "modules" / "uu.conf", "w", os.O_WRONLY))

    def test_protected_ruleset_write_requires_live_lease_in_production_mode(self):
        target = ROOT / "rulesets" / "review_cursor.json"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer.authorize_write_path(target)
                check.assert_called_once_with("rulesets/review_cursor.json")

    def test_resource_lease_guard_covers_every_repository_relative_path(self):
        protected_targets = (
            ROOT / "modules" / "adblock" / "scripts" / "Clean_Pro.js",
            ROOT / "scripts" / "build_rulesets.py",
            ROOT / "rulesets" / "direct.list",
            ROOT / "reports" / "audit.md",
            ROOT / "docs" / "operations.md",
            ROOT / "automation" / "task_queue.json",
            ROOT / "sources" / "discovered_sources.json",
            ROOT / "data" / "domain_candidates.json",
            ROOT / "README.md",
        )
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                for target in protected_targets:
                    fenced_file_writer.authorize_write_path(target)
                self.assertEqual(
                    [call.args[0] for call in check.call_args_list],
                    [
                        "modules/adblock/scripts/Clean_Pro.js",
                        "scripts/build_rulesets.py",
                        "rulesets/direct.list",
                        "reports/audit.md",
                        "docs/operations.md",
                        "automation/task_queue.json",
                        "sources/discovered_sources.json",
                        "data/domain_candidates.json",
                        "README.md",
                    ],
                )

    def test_non_repository_temporary_files_are_not_subject_to_repository_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
                with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                    fenced_file_writer.authorize_write_path(Path(directory) / "external.tmp")
                    check.assert_not_called()

    def test_local_unit_test_writes_do_not_require_a_production_lease(self):
        target = ROOT / "reports" / "review_cursor.json"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "0"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer.authorize_write_path(target)
                check.assert_not_called()

    def test_audit_hook_rejects_protected_config_unlink(self):
        with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
            fenced_file_writer._audit_hook("os.remove", (ROOT / "modules" / "uu.conf", -1))

    def test_audit_hook_checks_protected_open_before_write(self):
        target = ROOT / "modules" / "test-only.js"
        with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
            with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                fenced_file_writer._audit_hook("open", (target, "w", os.O_WRONLY | os.O_CREAT))
                check.assert_called_once_with("modules/test-only.js")

    def test_fenced_task_process_denies_all_child_process_creation_events(self):
        events = (
            "subprocess.Popen", "os.system", "os.exec", "os.spawn",
            "os.posix_spawn", "os.fork", "os.forkpty", "os.startfile", "pty.spawn",
        )
        with patch.dict(os.environ, {"AUTOMATION_TASK_PROCESS": "1"}, clear=False):
            for event in events:
                with self.subTest(event=event):
                    with self.assertRaisesRegex(
                        PermissionError, "child-process creation is prohibited"
                    ):
                        fenced_file_writer._audit_hook(event, ())

    def test_process_creation_policy_is_scoped_to_task_children(self):
        with patch.dict(os.environ, {"AUTOMATION_TASK_PROCESS": "0"}, clear=False):
            fenced_file_writer._audit_hook("subprocess.Popen", ())

    def test_audit_hook_denies_descriptor_based_mutation(self):
        with self.assertRaisesRegex(PermissionError, "descriptor-based filesystem mutations"):
            fenced_file_writer._audit_hook("os.utime", (7, None, None))

    def test_runtime_trace_records_only_repository_paths_and_no_file_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            target = ROOT / "rulesets" / "trace-fixture.json"
            with patch.dict(os.environ, {
                "AUTOMATION_WRITE_TRACE_PATH": str(trace),
                "GITHUB_WORKFLOW": "test-workflow",
                "GITHUB_RUN_ID": "12345",
                "AUTOMATION_TASK_ID": "task_example",
                "AUTOMATION_REQUIRE_RESOURCE_LEASE": "1",
            }, clear=False):
                fenced_file_writer._record_write_trace(target, "open")
                fenced_file_writer._record_write_trace(Path(directory) / "external.tmp", "open")
            rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["path"], "rulesets/trace-fixture.json")
            self.assertEqual(rows[0]["operation"], "open")
            self.assertEqual(rows[0]["workflow"], "test-workflow")
            self.assertEqual(rows[0]["run_id"], "12345")
            self.assertEqual(rows[0]["task_id"], "task_example")
            self.assertTrue(rows[0]["lease_required"])
            self.assertNotIn("contents", rows[0])

    def test_every_registered_python_component_installs_the_guard(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        components = [item for item in registry["programs"] if item.get("kind") == "python_component"]
        self.assertEqual(len(components), 54)
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

    def test_external_symlink_into_protected_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "config-link"
            alias.symlink_to(ROOT / "modules" / "uu.conf")
            with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
                fenced_file_writer.authorize_write_path(alias)

    def test_external_hardlink_to_protected_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "config-hardlink"
            os.link(ROOT / "modules" / "uu.conf", alias)
            with self.assertRaisesRegex(PermissionError, "owner-managed protected file"):
                fenced_file_writer.authorize_write_path(alias)

    def test_external_symlink_to_shared_ruleset_keeps_canonical_lease_key(self):
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "ruleset-link"
            alias.symlink_to(ROOT / "rulesets" / "direct.list")
            with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
                with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                    fenced_file_writer.authorize_write_path(alias)
                    check.assert_called_once_with("rulesets/direct.list")

    def test_external_hardlink_to_shared_ruleset_keeps_canonical_lease_key(self):
        with tempfile.TemporaryDirectory() as directory:
            alias = Path(directory) / "ruleset-hardlink"
            os.link(ROOT / "rulesets" / "direct.list", alias)
            with patch.dict(os.environ, {"AUTOMATION_REQUIRE_RESOURCE_LEASE": "1"}, clear=False):
                with patch("resource_lease_runtime.assert_resource_lease_from_environment") as check:
                    fenced_file_writer.authorize_write_path(alias)
                    check.assert_called_once_with("rulesets/direct.list")

    def test_repository_symlink_cannot_escape_to_external_directory(self):
        with tempfile.TemporaryDirectory() as external, tempfile.TemporaryDirectory(dir=ROOT) as inside:
            link = Path(inside) / "escape"
            link.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(PermissionError, "escapes through a symlink"):
                fenced_file_writer.authorize_write_path(link / "outside.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
