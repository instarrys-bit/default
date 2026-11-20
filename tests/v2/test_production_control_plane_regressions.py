from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from production_intent import classify_paths, load_manifest


class ProductionControlPlaneRegressionTests(unittest.TestCase):
    def test_storage_management_changes_do_not_block_ruleset_production(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            ".github/workflows/storage-management.yml",
            "storage/__init__.py",
            "storage/v2/artifact_store.py",
            "storage/v2/artifacts/catalog/43218826799.json",
            "storage/v2/artifacts/sha256/000b92d8f872de41b4bbaa62b92d70c7aca41e75c4c70b23ec0fd789542873f1",
        ]

        result = classify_paths(paths, manifest)

        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertCountEqual(result["non_production_changes"], paths)
        self.assertEqual(result["unknown_changes"], [])

    def test_unregistered_paths_still_require_review(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")

        result = classify_paths(["new/unregistered/control-plane.py"], manifest)

        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["unknown_changes"], ["new/unregistered/control-plane.py"])


class StorageManagementWorkflowRegressionTests(unittest.TestCase):
    def test_incident_store_cli_expands_the_bash_argument_array(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        invocations = [
            line.strip()
            for line in workflow.splitlines()
            if "python3 storage/v2/incident_store.py" in line
        ]

        self.assertEqual(len(invocations), 1)
        self.assertEqual(
            invocations[0],
            'python3 storage/v2/incident_store.py "${args[@]}" | tee "$GITHUB_STEP_SUMMARY"',
        )


class WatchdogQueueWriterPermissionRegressionTests(unittest.TestCase):
    def test_health_check_hands_off_queue_intent_to_the_write_capable_supervisor(self):
        workflow = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        health = workflow.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]

        self.assertIn("      contents: read", health)
        self.assertNotIn("      contents: write", health)
        self.assertIn(
            "queue_task_json: ${{ steps.failed-audit-recovery.outputs.queue_task_json || steps.stale-recovery.outputs.queue_task_json }}",
            health,
        )
        self.assertNotIn("enqueue-auto-sync", health)
        self.assertNotIn("task_scheduler.py", health)
        self.assertEqual(health.count('echo "queue_task_json=$queue_task_json" >> "$GITHUB_OUTPUT"'), 4)

        manifest = workflow.split("  manifest-integrity:", 1)[1]
        self.assertIn("queue_task_json: ${{ steps.integrity-recovery.outputs.queue_task_json }}", manifest)
        self.assertNotIn("enqueue-auto-sync", manifest)
        self.assertNotIn("task_scheduler.py", manifest)

        self.assertIn("      contents: write", queue)
        self.assertIn("Enqueue Watchdog production intent through queue writer", queue)
        self.assertIn("needs.health-check.outputs.queue_task_json || needs.manifest-integrity.outputs.queue_task_json", queue)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", queue)
        self.assertNotIn("secrets.AUTOMATION_WRITE_TOKEN", queue)
        self.assertIn("enqueue-auto-sync", queue)
        self.assertLess(
            queue.index("Enqueue Watchdog production intent through queue writer"),
            queue.index("Recover expired task and resource leases"),
        )

    def test_queue_write_token_has_contents_write_and_actions_write_only_in_queue_job(self):
        workflow = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        health = workflow.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]

        self.assertIn("      actions: write", health)
        self.assertIn("      contents: read", health)
        self.assertIn("      actions: write", queue)
        self.assertIn("      contents: write", queue)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", queue)


    def test_storage_management_state_writers_use_their_job_scoped_write_token(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        for job_name, next_job in (
            ("mutate-ledger", "poll-recent-actions-artifacts"),
            ("poll-recent-actions-artifacts", "ingest-actions-artifacts"),
            ("ingest-actions-artifacts", None),
        ):
            with self.subTest(job=job_name):
                block = workflow.split(f"  {job_name}:", 1)[1]
                if next_job:
                    block = block.split(f"  {next_job}:", 1)[0]
                self.assertIn("      contents: write", block)
                self.assertIn("GITHUB_TOKEN: ${{ github.token }}", block)
                self.assertNotIn("secrets.AUTOMATION_WRITE_TOKEN", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
