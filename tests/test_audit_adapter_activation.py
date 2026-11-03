import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_adapter_activation import (
    audit_activation_readiness, job_permissions, workflow_permission_sections,
)


class AdapterActivationAuditTests(unittest.TestCase):
    def test_repository_audit_is_read_only_and_does_not_enable_adapters(self):
        report = audit_activation_readiness(ROOT)
        self.assertTrue(report["read_only"])
        self.assertFalse(report["activation_performed"])
        self.assertEqual(report["program_count"], 54)
        self.assertEqual(report["adapter_count"], 54)
        self.assertEqual(report["enabled_adapter_count"], 2)
        self.assertTrue(report["watchdog_caller_permissions_ready"])
        self.assertEqual(
            [row["program_id"] for row in report["adapters"] if row["enabled"]],
            ["workflow_auto_sync", "workflow_self_healing_tests"],
        )

    def test_identifies_only_low_privilege_dispatchable_workflow_as_canary(self):
        report = audit_activation_readiness(ROOT)
        self.assertIn("workflow_self_healing_tests", report["least_privilege_canary_candidates"])
        for row in report["adapters"]:
            if row["least_privilege_canary_candidate"]:
                self.assertEqual(row["write_scopes"], [])
                self.assertEqual(row["side_effects"], [])

    def test_job_level_permissions_override_workflow_level_permissions(self):
        content = (
            "permissions:\n"
            "  actions: write\n"
            "  contents: read\n"
            "jobs:\n"
            "  health:\n"
            "    permissions:\n"
            "      issues: write\n"
            "  task-queue-supervision:\n"
            "    permissions:\n"
            "      actions: write\n"
            "      contents: write\n"
        )
        self.assertEqual(
            job_permissions(content, "task-queue-supervision"),
            {"actions": "write", "contents": "write"},
        )
        self.assertEqual(
            job_permissions(content, "health"),
            {"issues": "write"},
        )

    def test_permission_sections_capture_target_write_scopes(self):
        sections = workflow_permission_sections(
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  publish:\n"
            "    permissions:\n"
            "      contents: write\n"
        )
        self.assertEqual(sections, [
            {"contents": "read"},
            {"contents": "write"},
        ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
