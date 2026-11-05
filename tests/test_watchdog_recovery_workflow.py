import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


class WatchdogRecoveryWorkflowTests(unittest.TestCase):
    def test_watchdog_supervision_uses_cas_and_resource_fences_not_publisher_mutex(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        health = workflow.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("group: shadowrocket-watchdog-control-plane", health)
        self.assertIn("group: shadowrocket-watchdog-task-supervision", queue)
        self.assertNotIn("group: shadowrocket-watchdog-control-plane", queue)
        self.assertNotIn("group: shadowrocket-main-writer", health)
        self.assertNotIn("group: shadowrocket-main-writer", queue)
        self.assertIn("Git-blob-SHA CAS", health)
        self.assertIn("resource leases and fencing tokens", health)
        self.assertIn("cancel-in-progress: false", health)
        self.assertIn("cancel-in-progress: false", queue)
    def test_queue_supervision_is_isolated_from_health_checks_and_irrelevant_workflow_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("group: shadowrocket-watchdog-task-supervision", queue)
        self.assertIn("github.event_name != 'workflow_run'", queue)
        self.assertIn("github.event.workflow_run.name == 'Shadowrocket Deterministic Domain Audit (User Config Baseline)'", queue)
        self.assertIn("github.event.workflow_run.name == 'Shadowrocket Source Discovery (Watchdog)'", queue)
        self.assertNotIn("group: shadowrocket-watchdog-control-plane", queue)
        self.assertIn("cancel-in-progress: false", queue)
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", queue)

    def test_historical_dead_letter_resolution_is_not_scheduled(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertNotIn("Resolve superseded historical DEAD_LETTER tasks through queue CAS", workflow)
        self.assertNotIn("resolve-superseded-dead-letters", workflow)
        queue_job = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("Recover leases, verify results, and run one bounded task", queue_job)

    def test_watchdog_observes_completed_main_audit_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn('    - cron: "0 * * * *"', workflow)
        self.assertIn('      - "Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('      - "Shadowrocket Source Discovery (Watchdog)"', workflow)
        assessment_step = workflow.split("Enqueue source assessment after successful discovery workflow", 1)[1].split("Recover leases, verify results, and run one bounded task", 1)[0]
        self.assertIn("github.event.workflow_run.name == 'Shadowrocket Source Discovery (Watchdog)'", assessment_step)
        self.assertNotIn("github.event.workflow_run.name == 'Shadowrocket Deterministic Domain Audit (User Config Baseline)'", assessment_step)
        self.assertIn('      - "Validate Shadowrocket config against user baseline"', workflow)
        self.assertIn('      - "Validate self-healing agent"', workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn('last_success_sha="$(jq -r', workflow)
        self.assertIn('repos/$REPO/compare/$last_success_sha...$current_sha', workflow)
        self.assertIn("Normal input-change and scheduled-refresh decisions are centralized", workflow)
        self.assertIn("bash scripts/verify_publish_base.sh --check-only", workflow)

    def test_non_main_push_uses_main_merge_base_not_branch_before_sha(self):
        workflow = (ROOT / ".github" / "workflows" / "validate-config.yml").read_text(encoding="utf-8")
        recovery = workflow.split("name: Recover owner-approved config baseline in validation workspace", 1)[1].split("name: Verify owner-approved config baseline", 1)[0]
        self.assertIn('if [ "$GITHUB_EVENT_NAME" = "pull_request" ]', recovery)
        self.assertNotIn("github.event.pull_request.base.sha", recovery)
        self.assertIn('BASELINE_SOURCE_SHA="$(git merge-base origin/main "$GITHUB_SHA")"', recovery)
        self.assertNotIn("github.event.before", recovery)
        self.assertIn("BASELINE_SOURCE_REF", recovery)
        self.assertIn("BASELINE_SOURCE_EVENT", recovery)
        self.assertIn("python scripts/register_config_baseline.py", recovery)
    def test_only_infrastructure_failures_trigger_bounded_scheduled_or_push_recovery(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}', workflow)
        self.assertIn('SOURCE_EVENT: ${{ github.event.workflow_run.event }}', workflow)
        self.assertIn('SOURCE_WORKFLOW_NAME: ${{ github.event.workflow_run.name }}', workflow)
        self.assertIn("and self-healing failures have their own diagnosis paths.", workflow)
        self.assertIn("block_manifest=true", workflow)
        self.assertIn("needs.health-check.outputs.block_manifest != 'true'", workflow)
        self.assertIn('timed_out|startup_failure)', workflow)
        self.assertNotIn('failure|timed_out|startup_failure)', workflow)
        self.assertIn("scripts/watchdog_recovery_policy.py", workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "schedule" ]', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "push" ]', workflow)
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha and .id > $source', workflow)

    def test_stale_audit_reconciliation_uses_bounded_runs_and_durable_queue_evidence(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        stale = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split('          last_success_sha=', 1)[0]
        self.assertIn('runs="$(gh api "repos/$REPO/actions/workflows/auto_sync.yml/runs?per_page=100"', stale)
        self.assertNotIn("gh api --paginate --slurp", stale)
        self.assertIn("automation/task_queue.json", stale)
        self.assertIn("last_error.evidence.run_id", stale)
        self.assertIn("Stop stale audit before expensive deterministic review", stale)
        self.assertIn("production:guard-reconciliation:$current_fingerprint:$failed_run_id", stale)
        self.assertIn("while IFS=", stale)

    def test_run_history_checks_follow_all_api_pages(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 3)
        self.assertNotIn("runs?per_page=20", workflow)
        self.assertNotIn("runs?per_page=30", workflow)

    def test_workflow_dispatch_recovery_does_not_recursively_retry(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Workflow-dispatch run has no durable queue task correlation; refusing automatic recovery.", workflow)
        self.assertIn("github.event_name == 'workflow_run'", workflow)
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("A valid Watchdog task correlation is required", audit)
        self.assertIn('task.get("requester_program_id") != "workflow_automation_watchdog"', audit)
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', audit)

    def test_failed_run_cursor_normalizes_watchdog_correlation_to_canonical_task_id(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        cursor = audit.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn('canonical_task_id="${AUTOMATION_TASK_CORRELATION%%-a*}"', cursor)
        self.assertIn("assert-workflow --task-id \"$canonical_task_id\"", cursor)
        self.assertIn("assert-workflow --task-id \"$AUTOMATION_TASK_ID_BASE\"", cursor)
    def test_independent_source_discovery_has_fenced_immutable_handoff_and_stays_dormant(self):
        source = (ROOT / ".github" / "workflows" / "source-discovery.yml").read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        discovery_adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "workflow_source_discovery")
        discovery_program = next(x for x in registry["programs"] if x["id"] == "workflow_source_discovery")
        self.assertFalse(discovery_adapter["enabled"])
        self.assertFalse(discovery_program["orchestration"]["enabled"])
        self.assertEqual(discovery_adapter["workflow"]["path"], ".github/workflows/source-discovery.yml")
        self.assertIn("Verify exact Watchdog dispatch and install live resource fence", source)
        self.assertIn("resource_lease_runtime.py", source)
        self.assertIn("AUTOMATION_WRITE_GUARD: \"1\"", source)
        self.assertIn("Publish discovery inventory under its exact resource leases", source)
        self.assertIn("Upload immutable discovery artifact and provenance proof", source)
        self.assertIn("source-discovery-output", source)
        self.assertIn("Download artifact from the exact discovery workflow run", watchdog)
        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", watchdog)
        self.assertIn("Downloaded discovery artifact digest does not match its immutable proof.", watchdog)
        self.assertIn("The committed main discovery document no longer matches this producer artifact.", watchdog)
        self.assertIn("enqueue-source-discovery", watchdog)
        self.assertIn("Independent source discovery remains dormant", watchdog)
        # Keep the monolithic fallback until the independent adapter is authorized and live.
        self.assertIn("Discover candidate source repositories (non-activating)", audit)
        self.assertIn("Assess discovered rule-list syntax and policy claims", audit)
        auto_sync = next(x for x in adapters["adapters"] if x["target_program_id"] == "workflow_auto_sync")
        self.assertIn("sources/discovered_sources.json", auto_sync["resource_contract"]["resource_keys"])
        self.assertIn("reports/source-discovery.md", auto_sync["resource_contract"]["resource_keys"])

    def test_auto_sync_accepts_verifying_phase_resource_lease_after_task_lease_release(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        gate = audit.split("Verify Watchdog-owned durable task dispatch", 1)[1].split("Verify live Watchdog resource lease", 1)[0]
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', gate)
        self.assertIn('resource_lease.get("status") != "ACTIVE"', gate)
        self.assertIn('task_lease_token = lease.get("token") if isinstance(lease, dict) else "resource-fence-only"', gate)
        self.assertIn('workers.add(record.get("worker_id"))', gate)
        self.assertIn('"AUTOMATION_WORKER_ID": worker_id', gate)
        self.assertIn("resource lease owner is the write authority", gate)

    def test_successful_workflow_reports_degraded_source_discovery_health(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Report degraded source discovery health", workflow)
        self.assertIn(".source_discovery.search_error_count", workflow)
        self.assertIn(".coverage.stalled", workflow)
        self.assertIn("Shadowrocket source discovery degraded health", workflow)
        self.assertIn("gh issue create", workflow)
        self.assertIn("gh issue close", workflow)
        self.assertIn("issues: write", workflow)

    def test_successful_audit_writes_and_publishes_a_durable_heartbeat(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("Write successful audit heartbeat", workflow)
        self.assertIn('"status": "audit_passed"', workflow)
        self.assertIn('"modified_by_automation": False', workflow)
        self.assertIn("reports/automation/heartbeat.json", workflow)
        self.assertIn("git add --", workflow)


    def test_existing_heartbeat_and_stale_run_monitor_cover_distinct_health_signals(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        healing = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("reports/automation/heartbeat.json", audit)
        self.assertIn("Write successful audit heartbeat", audit)
        self.assertIn("stale-run-watch:", watchdog)
        self.assertNotIn("stale-run-watch:", healing)
        self.assertIn("run_started_at", watchdog)
        self.assertIn("21600", watchdog)
        self.assertIn('select(.status != "completed" and .head_branch == "main" and .id != null)', watchdog)
        self.assertIn('if .head_sha != $sha then', watchdog)
        self.assertIn("gh run cancel", watchdog)

    def test_top_level_watchdog_supervises_remote_queue_fail_closed(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("task-queue-supervision:", workflow)
        self.assertIn("needs.stale-run-watch.result == 'success'", workflow)
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", workflow)
        job_start = workflow.index("  task-queue-supervision:")
        job_end = workflow.index("  stale-run-watch:", job_start)
        queue_job = workflow[job_start:job_end]
        self.assertIn("      actions: write", queue_job)
        self.assertIn("      contents: write", queue_job)
        self.assertNotIn("      issues: write", queue_job)
        self.assertIn("persist-credentials: false", queue_job)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('queue_token="$GITHUB_TOKEN"', workflow)
        self.assertIn("unset GITHUB_TOKEN", workflow)
        self.assertIn("--token-stdin", workflow)
        self.assertIn("python3 scripts/task_scheduler.py", workflow)
        self.assertIn("--max-tasks 1 run-once", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)

    def test_production_audit_is_watchdog_queue_owned(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("enqueue_auto_sync_task", (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8"))
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        self.assertNotIn("  schedule:", audit.split("  workflow_dispatch:", 1)[0])
        self.assertNotIn("  push:", audit.split("  permissions:", 1)[0])
        self.assertIn("  workflow_dispatch:", audit)

    def test_watchdog_deduplicates_all_active_run_states_before_dispatch(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        for status in ("queued", "pending", "waiting", "requested", "in_progress"):
            self.assertIn(f'.status == "{status}"', workflow)
        self.assertIn("A deterministic audit for current main", workflow)

    def test_queue_and_activation_contract_changes_wake_the_watchdog(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        for path in (
            "automation/program_registry.json",
            "automation/execution_adapters.json",
        ):
            self.assertIn(f'      - "{path}"', workflow)
        self.assertNotIn('"automation/task_queue.json"', workflow.split("permissions:", 1)[0])
        self.assertNotIn('"rulesets/**"', workflow.split("permissions:", 1)[0])
        self.assertNotIn('"sources/**"', workflow.split("permissions:", 1)[0])
    def test_completion_dispatch_cannot_create_production_demand(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        step = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split("  task-queue-supervision:", 1)[0]
        self.assertIn("github.event_name == 'push'", step)
        self.assertIn("github.event_name == 'schedule'", step)
        self.assertIn("github.event_name == 'workflow_dispatch'", step)
        self.assertNotIn("github.event_name == 'repository_dispatch'", step)
        self.assertIn("repository_dispatch:", workflow)
        self.assertIn("automation-production-completed", workflow)

    def test_production_demand_is_fingerprint_based_and_single_sourced(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        health_start = workflow.index("      - name: Detect stale successful audit and recover")
        queue_start = workflow.index("  task-queue-supervision:", health_start)
        health = workflow[health_start:queue_start]
        self.assertIn("scripts/production_intent.py", health)
        self.assertIn("production_key=", health)
        self.assertIn('--idempotency-key "$production_key"', health)
        self.assertIn("REVIEW_REQUIRED", health)
        stale_start = workflow.index("  stale-run-watch:")
        manifest_start = workflow.index("  manifest-integrity:", stale_start)
        stale = workflow[stale_start:manifest_start]
        self.assertNotIn("audit_base_stale", stale)
        self.assertNotIn("auto-sync-stale:", stale)
        self.assertIn("bounded timeout recovery", stale)
        self.assertIn("production:recovery:$current_fingerprint:$timed_out_run_id", stale)

    def test_successful_heartbeat_persists_the_production_input_fingerprint(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("input_fingerprint", audit)
        self.assertIn("post_run_input_fingerprint", audit)
        self.assertIn("output_fingerprint", audit)
        self.assertIn("PRODUCTION_INPUT_FINGERPRINT", audit)
        self.assertIn("compute_fingerprint", audit)
        self.assertIn("automation/production_inputs.json", audit)

    def test_production_intent_engine_is_registered_and_ss_conf_is_read_only_input(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "automation" / "production_inputs.json").read_text(encoding="utf-8"))
        self.assertIn("script_production_intent", {item["id"] for item in registry["programs"]})
        self.assertIn("modules/uu.conf", manifest["production_input_paths"])
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        workflow_adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_auto_sync")
        declared_inputs = {item["name"] for item in workflow_adapter["workflow"]["inputs"]}
        self.assertTrue({"production_fingerprint", "production_decision", "production_reason"}.issubset(declared_inputs))

    def test_all_watchdog_recovery_dispatches_carry_auditable_production_intent(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("production:recovery:$recovery_fingerprint:$SOURCE_RUN_ID", workflow)
        self.assertIn("recomputing intent against current main", workflow)
        self.assertIn("production:input:$current_fingerprint", workflow)
        self.assertIn("production:integrity:$current_fingerprint", workflow)
        self.assertIn('production_decision:"RECOVERY_REQUIRED"', workflow)
        self.assertNotIn('idempotency-key "auto-sync-manifest:', workflow)

    def test_push_and_schedule_reconcile_only_audits_stopped_by_the_stale_base_guard(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('if [ "$ORIGIN_EVENT" = "push" ] || [ "$ORIGIN_EVENT" = "schedule" ]; then', workflow)
        self.assertIn('.name == "Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('and .status == "DEAD_LETTER"', workflow)
        self.assertIn('last_error.evidence.run_id', workflow)
        self.assertIn('production:guard-reconciliation:$current_fingerprint:$failed_run_id', workflow)
        self.assertIn('production_decision:"RECOVERY_REQUIRED"', workflow)
        self.assertIn("historical task $failed_task_id remains unchanged", workflow)
        self.assertIn("PENDING_CLASSIFICATION", workflow)
        self.assertIn('control.get("schema_version") == 1', workflow)
        self.assertIn('.target_program_id == "workflow_auto_sync"', workflow)
        self.assertIn('.[:20][]', workflow)

    def test_different_active_fingerprint_waits_instead_of_queuing_parallel_production(self):
        intent = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        self.assertIn("WAIT_FOR_ACTIVE", intent)
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("IN_PROGRESS|WAIT_FOR_ACTIVE|ALREADY_SATISFIED|OBSERVE_ONLY", workflow)

    def test_same_sha_failure_with_stale_task_fingerprint_is_reconciled(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("The task's input fingerprint is stale even if its workflow run SHA equals current main", workflow)
        self.assertIn("Same-SHA failure with an unchanged production fingerprint requires diagnosis", workflow)
        self.assertIn("production:input:$current_fingerprint", workflow)


    def test_watchdog_has_unique_job_environment_and_parseable_stale_run_script(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        queue_job = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertEqual(queue_job.count("\n    env:\n"), 1)
        self.assertIn('      PYTHONDONTWRITEBYTECODE: "1"', queue_job)
        stale_job = workflow.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn("fromdateiso8601", stale_job)
        self.assertIn("> 21600", stale_job)
        self.assertNotIn('CURRENT_MAIN="$current_main" RUNS_JSON=', stale_job)
        self.assertNotIn("python3 -c '", stale_job)
        self.assertNotIn('last_success="$(jq -r', workflow)


if __name__ == "__main__":
    unittest.main()
