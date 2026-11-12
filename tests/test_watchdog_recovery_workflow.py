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
        self.assertIn("group: shadowrocket-watchdog-control-plane-main", health)
        self.assertIn("group: shadowrocket-watchdog-task-supervision-main", queue)
        self.assertIn("coalesced workflow_run callbacks are recovered by the 15-minute schedule", queue)
        self.assertIn("timeout-minutes: 15", health)
        self.assertNotIn("group: shadowrocket-watchdog-control-plane", queue)
        self.assertNotIn("group: shadowrocket-main-writer", health)
        self.assertNotIn("group: shadowrocket-main-writer", queue)
        self.assertIn("Git-blob-SHA CAS", health)
        self.assertIn("resource leases and fencing tokens", health)
        self.assertIn("cancel-in-progress: false", health)
        self.assertIn("cancel-in-progress: false", queue)
        self.assertIn("logical/source-dag-supervision", (ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
    def test_queue_supervision_is_isolated_from_health_checks_and_irrelevant_workflow_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("group: shadowrocket-watchdog-task-supervision-main", queue)
        self.assertIn("github.event_name != 'workflow_run'", queue)
        self.assertIn("github.event.workflow_run.path == '.github/workflows/auto_sync.yml'", queue)
        self.assertIn("github.event.workflow_run.path == '.github/workflows/source-discovery.yml'", queue)
        self.assertNotIn("group: shadowrocket-watchdog-control-plane", queue)
        self.assertIn("cancel-in-progress: false", queue)
        self.assertIn("logical/source-dag-supervision", (ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", queue)
        self.assertIn("timeout-minutes: 15", queue)

    def test_historical_dead_letter_resolution_is_not_scheduled(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertNotIn("Resolve superseded historical DEAD_LETTER tasks through queue CAS", workflow)
        self.assertNotIn("resolve-superseded-dead-letters", workflow)
        queue_job = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("Recover leases, verify results, and dispatch one task before artifact upload", queue_job)

    def test_watchdog_observes_completed_main_audit_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn("run-name: Automation task ${{ inputs.automation_task_id || 'manual' }}", AUTO_SYNC.read_text(encoding="utf-8"))
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertIn('    - cron: "30 22 * * *"', workflow)
        trigger = workflow.split("  workflow_run:", 1)[1].split("  push:", 1)[0]
        self.assertIn("types: [completed]", trigger)
        self.assertIn('      - "Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('      - "Shadowrocket Source Discovery (Watchdog)"', workflow)
        health = workflow.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        for path in (
            ".github/workflows/auto_sync.yml",
            ".github/workflows/source-discovery.yml",
            ".github/workflows/validate-config.yml",
            ".github/workflows/self-healing-agent.yml",
        ):
            self.assertIn(path, health)
        assessment_step = workflow.split("Enqueue source assessment after successful discovery workflow", 1)[1].split("Recover leases, verify results, and dispatch one task before artifact upload", 1)[0]
        self.assertIn("steps.resolve-discovery-run.outputs.run_id", assessment_step)
        self.assertIn("steps.resolve-discovery-run.outputs.head_sha", assessment_step)
        resolver = workflow.split("Resolve completed Discovery run from durable task correlation", 1)[1].split("Download artifact from the exact discovery workflow run", 1)[0]
        self.assertIn("source-discovery.yml", resolver)
        self.assertIn("workflow_dispatch", resolver)
        self.assertIn("source-discovery-output", resolver)
        self.assertIn("head_sha", resolver)
        self.assertIn("artifact", resolver)
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
        self.assertIn('SOURCE_WORKFLOW_PATH: ${{ github.event.workflow_run.path }}', workflow)
        self.assertIn("and self-healing failures have their own diagnosis paths.", workflow)
        self.assertIn("block_manifest=true", workflow)
        self.assertIn("needs.health-check.outputs.block_manifest != 'true'", workflow)
        self.assertIn('timed_out|startup_failure|cancelled)', workflow)
        self.assertNotIn('failure|timed_out|startup_failure|cancelled)', workflow)
        self.assertIn("scripts/watchdog_recovery_policy.py", workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "schedule" ]', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "push" ]', workflow)
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha and .id > $source', workflow)

    def test_recovery_verifies_audit_workflow_by_path_and_registered_workflow_id(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        stale = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split('          last_success_sha=', 1)[0]
        self.assertIn('.path == ".github/workflows/auto_sync.yml"', stale)
        self.assertIn(".workflow_id == $workflow_id", stale)
        self.assertIn("dispatch_intent.workflow_id", stale)
        self.assertNotIn('.name == "Shadowrocket Deterministic Domain Audit (User Config Baseline)"', stale)

    def test_stale_audit_reconciliation_uses_bounded_runs_and_durable_queue_evidence(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        stale = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split('          last_success_sha=', 1)[0]
        self.assertIn('runs="$(gh api "repos/$REPO/actions/workflows/auto_sync.yml/runs?per_page=100"', stale)
        self.assertNotIn("gh api --paginate --slurp", stale)
        self.assertIn("AUTOMATION_QUEUE_SNAPSHOT", stale)
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

    def test_failed_run_cursor_recovery_is_artifact_only(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        cursor = audit.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions/download-artifact", cursor)
        self.assertIn("actions/upload-artifact", cursor)
        self.assertIn("failed-review-cursor-recovery", cursor)
        self.assertNotIn("contents: write", cursor)
        self.assertNotIn("assert-workflow", cursor)
        self.assertNotIn("git push", cursor)

    def test_assessment_batches_use_twenty_urls_and_bound_second_recovery_to_four(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("assessment_max_urls=20", workflow)
        self.assertIn('assessment_max_urls=4', workflow)
        self.assertIn('--argjson max_urls "$assessment_max_urls"', workflow)
        second_recovery = workflow.split('elif [ "$recovery_one_status" = "DEAD_LETTER" ]; then', 1)[1].split('elif [ -n "$recovery_one_status" ]', 1)[0]
        self.assertIn('assessment_max_urls=4', second_recovery)
        self.assertNotIn('assessment_max_urls=4', workflow.split('if [ "$assessment_status" = "DEAD_LETTER" ]; then', 1)[0])
        contract = json.loads((ROOT / "automation/capability_contracts/assess_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["inputs"]["remote_inputs"]["max_urls_per_run"], 20)
    def test_assessment_artifact_upload_output_uses_real_newlines(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        run_queue = workflow.split("name: Recover leases, verify results, and dispatch one task before artifact upload", 1)[1].split("name: Upload verified source assessment outputs as immutable artifact", 1)[0]
        self.assertIn('output.write(f"assessment_output_expected={value}\\n")', run_queue)
        self.assertNotIn('output.write(f"assessment_output_expected={value}\\\\n")', run_queue)
        self.assertIn("steps.run-queue.outputs.assessment_output_expected == 'true'", workflow)
        self.assertIn("Upload verified source assessment outputs as immutable artifact", workflow)
    def test_active_production_audit_is_cancelled_only_when_no_verified_assessment_exists(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Cancel active production audits while independent Assessment gate is closed", workflow)
        cancel = workflow.split("Cancel active production audits while independent Assessment gate is closed", 1)[1].split("Resolve completed Discovery run from durable task correlation", 1)[0]
        self.assertIn("latest_verified_assessed_discovery(tasks)", cancel)
        self.assertIn("newer unassessed Discovery tasks do not close the production gate", cancel)
        self.assertNotIn("latest = max(", cancel)
        self.assertNotIn("classify_assessment_handoff(tasks, run_id)", cancel)
        self.assertIn("validate_run_head_sha(client, intent, run.get(\"head_sha\"))", cancel)
        self.assertIn("/actions/runs/{run_id}/cancel", cancel)
        self.assertIn('task.get("target_program_id") != "workflow_auto_sync"', cancel)
        self.assertIn("Production run", cancel)
        self.assertIn("pre-assessment evidence, not an approved final publication", cancel)
        self.assertIn("fresh gated audit is required after Assessment", cancel)
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("production_source_assessment_gate(queue.get(\"tasks\", []), root)", scheduler)
        self.assertIn("verified non-activating Assessment", scheduler)

    def test_discovery_reconciliation_accepts_normal_run_state_progression_and_hashes_uploaded_files(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        resolver = watchdog.split("Resolve completed Discovery run from durable task correlation", 1)[1].split("Download artifact from the exact discovery workflow run", 1)[0]
        self.assertIn("Persisted Discovery run evidence conflicts with the verified run identity.", resolver)
        self.assertNotIn('evidence.get("status") != run.get("status")', resolver)
        self.assertNotIn('evidence.get("conclusion") != run.get("conclusion")', resolver)
        self.assertIn("Run status/conclusion are mutable lifecycle fields", resolver)
        self.assertIn("validate_run_head_sha(workflow_client, intent, run.get(\"head_sha\"))", resolver)
        self.assertIn("persisted_head_sha is not None", resolver)
        self.assertIn("persisted_relationship is not None", resolver)

        source = (ROOT / ".github" / "workflows" / "source-discovery.yml").read_text(encoding="utf-8")
        proof = source.split("Verify producer identity and prepare immutable artifact proof", 1)[1].split("Confirm discovery outputs remain runner-local", 1)[0]
        self.assertLess(proof.index("shutil.copy2(item"), proof.index("read_only_resource_digests(artifact_root"))
        self.assertIn('read_document(artifact_root / "sources/discovered_sources.json"', proof)
        self.assertIn('"artifact_sha256": digest', proof)
        self.assertIn("steps.verify-discovery-artifact.outputs.valid == 'false'", watchdog)
        self.assertIn("steps.verify-discovery-artifact.outputs.valid == 'true'", watchdog)
        self.assertIn("from source_handoff_policy import discovery_pipeline_revision", watchdog)
        self.assertIn("print(discovery_pipeline_revision(Path.cwd()))", watchdog)
        policy = (ROOT / "scripts" / "source_handoff_policy.py").read_text(encoding="utf-8")
        self.assertIn('".github/workflows/source-discovery.yml"', policy)

    def test_independent_source_discovery_and_assessment_are_enabled_with_runner_local_handoff(self):
        source = (ROOT / ".github" / "workflows" / "source-discovery.yml").read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        control = json.loads((ROOT / "automation" / "production_control.json").read_text(encoding="utf-8"))
        discovery_adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "workflow_source_discovery")
        discovery_program = next(x for x in registry["programs"] if x["id"] == "workflow_source_discovery")
        assessor = next(x for x in adapters["adapters"] if x["target_program_id"] == "script_assess_sources")
        assessor_program = next(x for x in registry["programs"] if x["id"] == "script_assess_sources")

        self.assertEqual(control["source_discovery_mode"], "independent")
        self.assertTrue(discovery_adapter["enabled"])
        self.assertEqual(discovery_adapter["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertTrue(discovery_program["orchestration"]["enabled"])
        self.assertEqual(discovery_program["orchestration"]["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertTrue(assessor["enabled"])
        self.assertEqual(assessor["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertTrue(assessor_program["orchestration"]["enabled"])
        self.assertEqual(assessor_program["orchestration"]["allowed_callers"], ["workflow_automation_watchdog"])

        self.assertEqual(discovery_adapter["workflow"]["path"], ".github/workflows/source-discovery.yml")
        self.assertIn("Verify exact Watchdog dispatch and install live resource fence", source)
        self.assertIn("resource_lease_runtime.py", source)
        self.assertNotIn("Publish discovery inventory under its exact resource leases", source)
        self.assertIn("Seed isolated discovery workspace from read-only main baseline", source)
        self.assertIn('AUTOMATION_TASK_PROCESS: "1"', source)
        self.assertIn("AUTOMATION_ARTIFACT_ROOT", source)
        self.assertIn("Confirm discovery outputs remain runner-local", source)
        self.assertNotIn("git push", source)
        self.assertIn("Upload immutable discovery artifact and provenance proof", source)
        self.assertIn("source-discovery-output", source)

        self.assertIn("Download artifact from the exact discovery workflow run", watchdog)
        self.assertIn("Resolve completed Discovery run from durable task correlation", watchdog)
        self.assertIn("dispatch_intent", watchdog)
        self.assertIn("AUTOMATION_QUEUE_SNAPSHOT", watchdog)
        self.assertIn("RUNNER_TEMP", watchdog)
        self.assertIn('"SUCCEEDED"', watchdog)
        self.assertIn("queue_path.read_text", watchdog)
        self.assertIn("requested_head_sha", watchdog)
        self.assertIn("correlation_id", watchdog)
        self.assertIn("workflow_dispatch", watchdog)
        self.assertIn("classify_assessment_handoff(tasks, run_id)", watchdog)
        self.assertIn('base_key="source-assessment:$SOURCE_RUN_ID:parser-v2"', watchdog)
        self.assertIn('--idempotency-key "$assessment_key"', watchdog)
        self.assertIn('task.get("target_program_id") == "script_assess_sources"', watchdog)
        self.assertIn('task.get("status") == "QUEUED"', watchdog)
        self.assertIn('workflow_client.list_runs(workflow_id, "main", page)', watchdog)
        self.assertIn("if page > 20:", watchdog)
        self.assertIn('"$base_key:recovery:1"', watchdog)
        self.assertIn('"$base_key:recovery:2"', watchdog)
        self.assertIn('proof.get("workflow_run_id", "")', watchdog)
        self.assertIn('actions/runs/{run_id}', watchdog)
        self.assertIn("Queued Assessment predecessor does not resolve to its exact successful Discovery run.", watchdog)
        self.assertIn("steps.resolve-discovery-run.outputs.run_id", watchdog)
        self.assertIn("steps.resolve-discovery-run.outputs.head_sha", watchdog)
        self.assertIn("exact successful Discovery run must have exactly one unexpired source-discovery-output artifact", watchdog)
        self.assertIn("run-id: ${{ steps.resolve-discovery-run.outputs.run_id }}", watchdog)
        self.assertIn("Downloaded discovery artifact digest does not match its immutable proof; Assessment is blocked", watchdog)
        self.assertNotIn("The committed main discovery document no longer matches this producer artifact.", watchdog)
        self.assertIn("no sources/ commit is required", watchdog)
        self.assertIn("enqueue-source-discovery", watchdog)
        self.assertIn("steps.source-mode.outputs.mode", watchdog)
        self.assertIn("Resolve source execution mode from production control", watchdog)
        self.assertIn("Independent source discovery remains dormant", watchdog)

        # The monolithic implementation remains only as an explicit rollback path.
        self.assertIn("if: ${{ steps.source-mode.outputs.mode != 'independent' }}", audit)
        self.assertIn("Discover candidate source repositories (non-activating)", audit)
        self.assertIn("Assess discovered rule-list syntax and policy claims", audit)
        self.assertIn("Resolve source execution mode from production control", audit)
        self.assertIn("Upload verified source assessment outputs as immutable artifact", watchdog)
        auto_sync = next(x for x in adapters["adapters"] if x["target_program_id"] == "workflow_auto_sync")
        self.assertIn("sources/discovered_sources.json", auto_sync["resource_contract"]["resource_keys"])
        self.assertIn("reports/source-discovery.md", auto_sync["resource_contract"]["resource_keys"])

    def test_source_reconciliation_scans_all_pages_and_recovers_queued_assessment_predecessors(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("while page <= 20:", watchdog)
        self.assertIn("page += 1", watchdog)
        self.assertIn("Discovery workflow run history exceeds the bounded 2,000-run reconciliation window", watchdog)
        self.assertIn('task.get("status") == "QUEUED"', watchdog)

    def test_source_discovery_retries_once_after_a_dead_lettered_daily_task(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('base_status="$(jq -r', watchdog)
        self.assertIn('"$base_key:recovery:1"', watchdog)
        self.assertIn('[ "$base_status" = "DEAD_LETTER" ]', watchdog)
        self.assertIn('if [ -n "$recovery_key" ]; then', watchdog)

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
        self.assertIn("      contents: read", queue_job)
        self.assertIn("      issues: write", queue_job)
        self.assertIn("persist-credentials: false", queue_job)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('queue_token="$GITHUB_TOKEN"', workflow)
        self.assertIn("unset GITHUB_TOKEN", workflow)
        self.assertIn("--token-stdin", workflow)
        self.assertIn("python3 scripts/task_scheduler.py", workflow)
        self.assertIn("--max-tasks 1 run-once", workflow)
        self.assertIn("dispatch one task before artifact upload", workflow)
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
    def test_production_completion_reconciles_only_after_workflow_run_completes(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        step = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split("  task-queue-supervision:", 1)[0]
        self.assertIn("github.event_name == 'push'", step)
        self.assertIn("github.event_name == 'schedule'", step)
        self.assertIn("github.event_name == 'workflow_dispatch'", step)
        self.assertNotIn("repository_dispatch:", workflow)
        self.assertNotIn("automation-production-completed", workflow)
        self.assertIn("workflow_run:", workflow)
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertNotIn("notify-watchdog-completion:", audit)
        self.assertNotIn("automation-production-completed", audit)

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
        self.assertIn('.path == ".github/workflows/auto_sync.yml"', workflow)
        self.assertIn(".workflow_id == $workflow_id", workflow)
        self.assertIn("dispatch_intent.workflow_id", workflow)
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


    def test_watchdog_excludes_deleted_non_production_paths_from_unknown_path_registration(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('.files[] | . as $file', workflow)
        self.assertIn('$file.status != "removed"', workflow)
        self.assertIn('$manifest[0].production_input_paths | index($file.filename)', workflow)

    def test_independent_source_resource_leases_outlive_watchdog_reconciliation_window(self):
        import re
        workflow = WATCHDOG.read_text(encoding="utf-8")
        match = re.search(r'cron:\s*"\*/([0-9]+) \* \* \* \*"', workflow)
        self.assertIsNotNone(match, "Watchdog reconciliation cron must be explicit")
        reconciliation_seconds = int(match.group(1)) * 60
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        by_id = {item["target_program_id"]: item for item in adapters["adapters"]}
        for program_id in ("workflow_source_discovery", "script_assess_sources"):
            with self.subTest(program_id=program_id):
                lease_seconds = by_id[program_id]["resource_contract"]["lease_seconds"]
                self.assertGreaterEqual(lease_seconds, reconciliation_seconds * 4)
        contract = json.loads((ROOT / "automation" / "capability_contracts" / "assess_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["resource_contract"]["lease_seconds"], by_id["script_assess_sources"]["resource_contract"]["lease_seconds"])

    def test_discovery_handoff_reuses_verified_run_evidence_and_accepts_queue_intent_commit_sha(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        resolver = workflow.split("Resolve completed Discovery run from durable task correlation", 1)[1].split("Download artifact from the exact discovery workflow run", 1)[0]
        self.assertIn('evidence = (task.get("result") or {}).get("run_evidence")', resolver)
        self.assertIn("validate_run_head_sha(workflow_client, intent, run.get(\"head_sha\"))", resolver)
        self.assertIn("head_sha_relationship", resolver)
        self.assertIn("expected_correlation_titles(intent)", resolver)
        self.assertIn('sys.path.insert(0, "scripts")', resolver)
        self.assertNotIn("run.get(\"head_sha\") == requested_sha", resolver)
        self.assertIn("classify_assessment_handoff(tasks, run_id)", resolver)
        self.assertIn("handoff_state", resolver)
        self.assertNotIn("parser-v2", resolver)
        self.assertIn('base_key="source-assessment:$SOURCE_RUN_ID:parser-v2"', workflow)
        self.assertIn('--idempotency-key "$assessment_key"', workflow)


    def test_existing_assessment_suppresses_duplicate_enqueue_and_replacement_discovery(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        resolver = workflow.split("Resolve completed Discovery run from durable task correlation", 1)[1].split("Download artifact from the exact discovery workflow run", 1)[0]
        enqueue_assessment = workflow.split("Enqueue source assessment after successful discovery workflow", 1)[1].split("Enqueue independent source discovery only after its authorization gate opens", 1)[0]
        self.assertIn("Enqueue one artifact-recovery Assessment after verified success without supervisor upload", enqueue_assessment)
        self.assertIn("artifact-recovery:1", enqueue_assessment)
        enqueue_discovery = workflow.split("Enqueue independent source discovery only after its authorization gate opens", 1)[1].split("Recover leases, verify results, and dispatch one task before artifact upload", 1)[0]
        self.assertIn("classify_assessment_handoff(tasks, run_id)", resolver)
        self.assertIn("duplicate_assessment_task_ids", resolver)
        self.assertIn("awaiting_discovery_run", resolver)
        self.assertIn("handoff_state == 'ready'", enqueue_assessment)
        self.assertIn("handoff_state == 'assessment_retry_required'", enqueue_assessment)
        self.assertIn('source-assessment:$SOURCE_RUN_ID:parser-v2', enqueue_assessment)
        self.assertIn('recovery:1', enqueue_assessment)
        self.assertIn('recovery:2', enqueue_assessment)
        self.assertIn('{max_urls:20,max_file_bytes:1000000,max_total_bytes:10000000,predecessor:$predecessor}', enqueue_assessment)
        self.assertIn("handoff_state == ''", enqueue_discovery)
        self.assertNotIn("parser-v2", resolver)

    def test_watchdog_prioritizes_queued_production_before_next_source_worker(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        worker = workflow.split(
            "Recover leases, verify results, and dispatch one task before artifact upload", 1
        )[1].split("Upload verified source assessment outputs as immutable artifact", 1)[0]
        self.assertIn("select_production_worker_task(tasks, current_fingerprint)", worker)
        self.assertIn("Deferring the next source worker", worker)
        self.assertLess(
            worker.index("production_task_id = select_production_worker_task"),
            worker.index("print(select_source_worker_task(tasks))"),
        )
        self.assertIn("active_production = any(", worker)

    def test_discovery_handoff_resolver_initializes_api_context_before_artifact_lookup(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        resolver = workflow.split("      - name: Resolve completed Discovery run from durable task correlation", 1)[1].split(
            "      - name: Download artifact from the exact discovery workflow run", 1
        )[0]
        self.assertIn('repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]', resolver)
        self.assertLess(
            resolver.index('repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]'),
            resolver.index("find_matching_assessment_artifact("),
        )

    def test_stale_production_task_cancellation_is_a_safe_no_dispatch_outcome(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('task.get("status") == "CANCELLED"', workflow)
        self.assertIn('error.get("type") == "stale_production_input_superseded"', workflow)
        self.assertIn('"disposition": "stale_input_safely_superseded"', workflow)
        self.assertIn('raise SystemExit("Selected production task was cancelled for a reason requiring diagnosis:', workflow)


class WatchdogStaleRunRecoveryTests(unittest.TestCase):
    def test_push_and_scheduled_runs_recover_orphaned_watchdog_workers(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        stale = workflow.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn("github.event_name == 'push'", stale)
        self.assertIn("CURRENT_WATCHDOG_RUN_ID: ${{ github.run_id }}", stale)
        self.assertIn("actions/workflows/automation-watchdog.yml/runs?per_page=100", stale)
        self.assertIn("(.id | tostring) != $current", stale)
        self.assertIn("(now - $started) > 1800", stale)
        self.assertIn('gh run cancel "$stale_id"', stale)
        self.assertIn('if [ "$status" != "completed" ]; then', stale)
        self.assertIn("cancellation is not confirmed", stale)

    def test_superseded_audit_is_cancelled_when_it_exceeds_six_hour_runtime(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        stale = workflow.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        age_check = stale.index("if $started != null and (now - $started) > 21600 then")
        superseded_check = stale.index("elif .head_sha != $sha then")
        self.assertLess(age_check, superseded_check)
        self.assertIn('[.id, "timeout", (.head_sha // "")]', stale)
        self.assertIn('if [ "$reason" = "timeout" ]; then timed_out_any=1;', stale)

    def test_queue_supervision_fails_closed_when_stale_run_recovery_fails(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        queue = workflow.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("(github.event_name == 'workflow_run' || needs.stale-run-watch.result == 'success')", queue)
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", queue)

if __name__ == "__main__":
    unittest.main()
