import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "auto_sync.yml"
WATCHDOG_WORKFLOW = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
STORAGE_WORKFLOW = ROOT / ".github" / "workflows" / "storage-management.yml"
DASHBOARD_WORKFLOW = ROOT / ".github" / "workflows" / "dashboard-pages.yml"


class WorkflowConfigGuardOrderTests(unittest.TestCase):
    def test_stale_audit_guard_runs_before_expensive_domain_review(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        early_guard = workflow.index("Stop stale audit before discovery and source downloads")
        discovery = workflow.index("Discover candidate source repositories (non-activating)")
        guard = workflow.index("Stop stale audit before expensive deterministic review")
        review = workflow.index(
            "Audit each domain: deduplicate, resolve conflicts, grade evidence and protect critical services"
        )
        self.assertLess(early_guard, discovery)
        self.assertLess(guard, review)
        self.assertEqual(workflow.count("bash scripts/verify_publish_base.sh --check-only"), 2)
        publish_guard = (ROOT / "scripts" / "verify_publish_base.sh").read_text(encoding="utf-8")
        self.assertIn("Only strictly verified durable queue-state commits changed", publish_guard)
        self.assertIn(
            "A declared production input changed after the audited commit; a new production audit is required.",
            publish_guard,
        )
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("Keep the active audit; stale-commit guards stop obsolete runs safely.", workflow)
        self.assertIn("group: shadowrocket-main-writer", workflow)
        self.assertIn("Independently verify committed remote rulesets", workflow)
        self.assertLess(
            workflow.index("git push origin HEAD:main"),
            workflow.index("Independently verify committed remote rulesets"),
        )

    def test_v2_four_workflow_boundary(self):
        workflow_dir = ROOT / ".github" / "workflows"
        names = sorted(p.name for p in workflow_dir.glob("*.yml"))
        self.assertEqual(
            names,
            [
                "auto_sync.yml",
                "automation-watchdog.yml",
                "dashboard-pages.yml",
                "storage-management.yml",
            ],
        )

    def test_watchdog_control_plane_is_serialized_and_main_only(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-automation-watchdog-${{ github.run_id }}", watchdog)
        self.assertIn("group: shadowrocket-watchdog-task-supervision-main", watchdog)
        self.assertIn("cancel-in-progress: false", watchdog)
        self.assertIn("github.ref == 'refs/heads/main'", watchdog)
        self.assertIn("production_intent.py", watchdog)
        self.assertIn("enqueue-auto-sync", watchdog)
        self.assertIn("run-once", watchdog)

    def test_main_writers_are_serialized_and_retired_intake_is_absent(self):
        auto_sync = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-main-writer", auto_sync)
        self.assertFalse((ROOT / ".github" / "workflows" / "request-intake.yml").exists())
        self.assertFalse((ROOT / ".github" / "workflows" / "self-healing-agent.yml").exists())
        self.assertTrue(STORAGE_WORKFLOW.is_file())
        self.assertTrue(DASHBOARD_WORKFLOW.is_file())

    def test_watchdog_does_not_own_retired_manifest_or_assessment_gate_jobs(self):
        """V2 watchdog is intent+supervision only; retired multi-job control plane is gone."""
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("manifest-integrity:", watchdog)
        self.assertNotIn(
            "Cancel active production audits while independent Assessment gate is closed", watchdog
        )
