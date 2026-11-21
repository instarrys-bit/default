import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
AUTO_SYNC = WORKFLOWS / "auto_sync.yml"
WATCHDOG = WORKFLOWS / "automation-watchdog.yml"
STORAGE = WORKFLOWS / "storage-management.yml"
DASHBOARD = WORKFLOWS / "dashboard-pages.yml"


class UnifiedAutomationArchitectureTests(unittest.TestCase):
    def test_only_four_active_workflows_remain(self):
        active = {path.name for path in WORKFLOWS.glob("*.yml")}
        self.assertEqual(active, {
            "auto_sync.yml", "automation-watchdog.yml",
            "dashboard-pages.yml", "storage-management.yml",
        })
        for retired in (
            "self-healing-agent.yml", "source-discovery.yml",
            "assessment-completion-relay.yml", "queue-snapshot-artifact.yml",
            "storage-incident-management.yml",
        ):
            self.assertFalse((WORKFLOWS / retired).exists())

    def test_watchdog_is_the_top_level_durable_scheduler(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertIn('    - cron: "30 22 * * *"', workflow)
        self.assertIn("  health-check:", workflow)
        self.assertIn("  task-queue-supervision:", workflow)
        self.assertIn("remote_task_queue_runtime.py", workflow)
        self.assertIn("--max-tasks 1 run-once", workflow)
        self.assertIn("needs: [health-check]", workflow)

    def test_queue_writer_is_serialized_and_uses_storage_management_cas(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        queue_store = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-watchdog-queue-writer-main", watchdog)
        self.assertIn("automation/task_queue.json", queue_store)
        self.assertIn("GitHubContentsJsonStore", queue_store)
        self.assertIn("sha", queue_store.lower())
        self.assertIn("path not in ALLOWED_STATE_PATHS", queue_store)

    def test_storage_management_owns_incident_and_queue_state_paths(self):
        workflow = STORAGE.read_text(encoding="utf-8")
        queue_store = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        incident_store = (ROOT / "storage" / "v2" / "incident_store.py").read_text(encoding="utf-8")
        self.assertIn("  mutate-ledger:", workflow)
        self.assertIn("choices: [record, resolve]", workflow)
        self.assertIn("automation/task_queue.json", queue_store)
        self.assertIn("storage/v2/incidents.json", incident_store)
        self.assertIn("contents: write", workflow)
        self.assertNotIn("gh issue", workflow)
        self.assertNotIn("/issues/", workflow)

    def test_incident_recovery_requires_https_verification_and_state_transition(self):
        source = (ROOT / "storage" / "v2" / "incident_store.py").read_text(encoding="utf-8")
        state = (ROOT / "scripts" / "incident_state.py").read_text(encoding="utf-8")
        self.assertIn('verification_url.startswith("https://")', source)
        self.assertIn('target_state="VERIFYING"', source)
        self.assertIn('target_state="RECOVERED"', source)
        self.assertIn("incident-state:v1", state)
        self.assertIn("incident_key(workflow, source_sha, classification)", source)

    def test_protected_config_is_owner_controlled_and_never_a_publish_target(self):
        policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
        guard = policy["managed_config_guard"]
        self.assertFalse(guard["content_protection"]["automation_may_modify_content"])
        writes = json.loads((ROOT / "automation" / "resource_write_sets.json").read_text(encoding="utf-8"))
        protected = writes["policy"]["protected_config"]
        self.assertEqual(protected["access"], "read_only")
        self.assertEqual(protected["writers_allowed"], [])
        for entry in writes["confirmed_write_sets"]:
            self.assertNotIn("modules/uu.conf", entry.get("writes", []))
            self.assertNotIn("modules/uu.conf", entry.get("publish_resources", []))
        baseline = (ROOT / "scripts" / "register_config_baseline.py").read_text(encoding="utf-8")
        self.assertNotIn("--apply", baseline)

    def test_failed_review_cursor_is_retained_as_an_immutable_artifact(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions: write", cursor)
        self.assertIn("actions/upload-artifact", cursor)
        self.assertIn("failed-review-cursor-recovery", cursor)
        self.assertNotIn("contents: write", cursor)
        self.assertNotIn("git add", cursor)
        self.assertNotIn("git push", cursor)

    def test_stale_inputs_are_blocked_before_expensive_work_and_publication(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("Stop stale audit before discovery and source downloads", workflow)
        self.assertIn("Stop stale audit before expensive deterministic review", workflow)
        self.assertIn("verify_publish_base.sh", workflow)
        self.assertIn("Verify base commit and safely publish allowlisted outputs", workflow)
        self.assertIn("Independently verify committed remote rulesets", workflow)
        self.assertIn("git diff --quiet", workflow)
        self.assertIn("modules/uu.conf", workflow)

    def test_watchdog_retry_policy_is_bounded_to_infrastructure_failures(self):
        policy = (ROOT / "scripts" / "watchdog_recovery_policy.py").read_text(encoding="utf-8")
        self.assertIn('RETRYABLE_CONCLUSIONS = {"timed_out", "startup_failure", "cancelled"}', policy)
        self.assertIn("max_retries: int = 2", policy)
        self.assertIn("base_cooldown: timedelta = timedelta(minutes=15)", policy)

    def test_dashboard_is_read_only(self):
        workflow = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("actions: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("actions: write", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
