import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "auto_sync.yml"
WATCHDOG_WORKFLOW = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


class WorkflowConfigGuardOrderTests(unittest.TestCase):
    def test_stale_audit_guard_runs_before_expensive_domain_review(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        early_guard = workflow.index("Stop stale audit before discovery and source downloads")
        discovery = workflow.index("Discover candidate source repositories (non-activating)")
        guard = workflow.index("Stop stale audit before expensive deterministic review")
        review = workflow.index("Audit each domain: deduplicate, resolve conflicts, grade evidence and protect critical services")
        self.assertLess(early_guard, discovery)
        self.assertLess(guard, review)
        self.assertEqual(workflow.count("bash scripts/verify_publish_base.sh --check-only"), 2)
        publish_guard = (ROOT / "scripts" / "verify_publish_base.sh").read_text(encoding="utf-8")
        self.assertIn("Only strictly verified durable queue-state commits changed", publish_guard)
        self.assertIn('A declared production input changed after the audited commit; a new production audit is required.', publish_guard)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("Keep the active audit; stale-commit guards stop obsolete runs safely.", workflow)
        self.assertIn("group: shadowrocket-main-writer", workflow)
        self.assertIn("Independently verify committed remote rulesets", workflow)
        self.assertLess(workflow.index("git push origin HEAD:main"), workflow.index("Independently verify committed remote rulesets"))

    def test_watchdog_recovery_is_main_only_and_serialized_with_publisher(self):
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-main-writer", watchdog)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", watchdog)
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha', watchdog)
        self.assertIn('select(.head_branch == "main" and .conclusion == "success")', watchdog)

    def test_main_writers_are_serialized_or_use_safe_rebase(self):
        auto_sync = WORKFLOW.read_text(encoding="utf-8")
        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-main-writer", auto_sync)
        # Intake appends validated observations to Issue #317 and never writes repository files.
        self.assertIn("group: shadowrocket-domain-intake", intake)
        self.assertIn("contents: read", intake)
        self.assertIn("issues: write", intake)
        self.assertIn("issues/317/comments", intake)
        self.assertNotIn("git add", intake)
        self.assertNotIn("git commit", intake)
        self.assertNotIn("git push", intake)
        manifest_writer = watchdog.split("  manifest-integrity:", 1)[1]
        self.assertIn("group: shadowrocket-main-writer", manifest_writer)
        self.assertNotIn("github-only-domain-intake", intake)

    def test_request_intake_replays_same_run_batch_against_latest_main_without_force_push(self):
        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        self.assertIn("Append observation batch to external intake Issue", intake)
        self.assertIn("shadowrocket-domain-observation:v1", intake)
        self.assertIn("issues/317/comments", intake)
        self.assertIn("request_deterministic_audit=true", intake)
        self.assertNotIn("git add", intake)
        self.assertNotIn("git commit", intake)
        self.assertNotIn("git push", intake)

    def test_request_intake_validation_and_dispatch_handoff_are_well_formed(self):
        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        # Every embedded Python heredoc must terminate; this catches the original
        # shell parse failure that swallowed the following workflow steps.
        self.assertEqual(intake.count("<<'PY'"), intake.splitlines().count("          PY"))
        self.assertIn("id: validate", intake)
        self.assertIn('output.write("has_domains=false\\n")', intake)
        self.assertIn('output.write("has_domains=true\\n")', intake)
        self.assertIn('if: steps.validate.outputs.has_domains == \'true\'', intake)
        self.assertEqual(intake.count("if: steps.validate.outputs.has_domains == 'true'"), 2)
        self.assertIn("GH_TOKEN: ${{ github.token }}", intake)
        self.assertNotIn("\\${{ github.token }}", intake)
        self.assertNotIn("\\${{ github.repository }}", intake)
        self.assertNotIn("\\${{ github.run_id }}", intake)
        self.assertNotIn("\\${{ github.actor }}", intake)
        self.assertIn('gh workflow run automation-watchdog.yml --ref main', intake)

    def test_self_healing_never_cancels_non_main_runs_or_cross_closes_incidents(self):
        healing = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('select(.status != "completed" and .head_branch == "main" and .id != null)', watchdog)
        self.assertNotIn("gh run cancel", healing)
        self.assertIn('select(.head_branch == "main" and .id > $failed)', healing)
        self.assertIn("workflow=deterministic_audit;run_id=", healing)
        self.assertIn("workflow=config_validator;run_id=", healing)
        self.assertIn('workflow_key="config_validator"', healing)
        self.assertIn('workflow_key="deterministic_audit"', healing)
        self.assertIn('title="Self-healing incident: $classification ($workflow_key; ${FAILED_SHA:0:8})"', healing)
        self.assertIn('title="Self-healing agent failure: $workflow_key (source run $SOURCE_RUN_ID)"', healing)
        self.assertNotIn("gh issue close", healing)
        self.assertEqual(healing.count('close_issue "$issue"'), 2)
        self.assertEqual(healing.count('gh api --method PATCH "repos/$REPO/issues/$issue_number" -f state=closed >/dev/null'), 2)
        in_incident_command = False
        for line in healing.splitlines():
            if "python3 scripts/incident_state.py" in line:
                in_incident_command = True
            if in_incident_command:
                self.assertFalse(line.endswith("\\\\"), line)
                if "--out " in line:
                    in_incident_command = False

    def test_automation_incidents_are_bound_to_exact_workflow_runs(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Shadowrocket automation incident (run $RUN_ID)", workflow)
        self.assertIn("workflow=auto_sync;run_id=$RUN_ID", workflow)
        self.assertIn("capture(\"shadowrocket-automation:workflow=auto_sync;run_id=", workflow)
        resolver = workflow.split("  resolve-failure:", 1)[1]
        self.assertIn("Shadowrocket automation failure (run ", resolver)
        self.assertIn("Shadowrocket automation incident (run ", resolver)
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("Close recovered manifest integrity incidents", watchdog)
        self.assertIn("steps.verify.outcome == 'success'", watchdog)

    def test_high_volume_state_is_restored_before_candidate_mutation(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        restore = workflow.index("Restore prior high-volume automation state")
        import_observations = workflow.index("Import observed request hostnames as unclassified candidates")
        collect = workflow.index("Collect and cross-check all enabled domain sources")
        self.assertLess(restore, import_observations)
        self.assertLess(restore, collect)
        self.assertIn("actions: read", workflow)
        self.assertIn("retention-days: 90", workflow)
        self.assertIn("fail_closed", workflow)

    def test_state_pointer_is_in_audit_archive_before_publish(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        package = workflow.split("      - name: Package allowlisted audit outputs", 1)[1].split(
            "      - name: Upload allowlisted audit outputs", 1
        )[0]
        self.assertIn("reports/automation/state_store.json", package)
        self.assertIn("declare -A archive_seen=()", package)
        self.assertIn('tar -czf "$RUNNER_TEMP/audit-output.tar.gz" -- "${archive_inputs[@]}"', package)
        self.assertIn("data/domain_candidates.json", package)

    def test_large_state_is_artifact_backed_not_committed_as_giant_json(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publish = workflow.split("      - name: Verify base commit and safely publish allowlisted outputs", 1)[1]
        allowlist = publish.split("          publish_paths=(", 1)[1].split("          )", 1)[0]
        for path in ("sources/domain_reviews.json", "sources/review_cursor.json",
                     "sources/rule_provenance.json", "data/domain_candidates.json",
                     "data/candidates.json", "data/source_pending.json", "data/source_snapshots/"):
            self.assertNotIn(path, allowlist)
        self.assertEqual([x.strip() for x in allowlist.splitlines() if x.strip()], ["rulesets/"])
        self.assertIn('if [[ -e "$path" ]]', publish)
        self.assertIn('git add -- "$path"', publish)

    def test_config_conflicts_are_checked_before_and_after_rule_mutations(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        pre = workflow.index("Remove published and queued rules that conflict with uu.conf")
        collect = workflow.index("Collect and cross-check all enabled domain sources")
        build = workflow.index("Build standalone DIRECT, PROXY and REJECT rule sets")
        lifecycle = workflow.index("Run conservative lifecycle audit and selectable restoration")
        final = workflow.index("Reconcile final uu.conf scope coverage after all rule mutations")
        validate = workflow.index("Validate Shadowrocket config structure")
        self.assertLess(pre, collect)
        self.assertLess(collect, build)
        self.assertLess(build, lifecycle)
        self.assertLess(lifecycle, final)
        self.assertLess(final, validate)

    def test_config_conflict_sync_is_run_at_both_guard_points(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python3 scripts/sync_ruleset_config_conflicts.py"), 2)

    def test_publisher_uses_dedicated_safe_base_guard(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("bash scripts/verify_publish_base.sh", workflow)
        guard = (ROOT / "scripts" / "verify_publish_base.sh").read_text(encoding="utf-8")
        self.assertIn('git merge-base --is-ancestor "$GITHUB_SHA" origin/main', guard)
        self.assertIn("docs/*)", guard)
        self.assertIn('git reset --hard origin/main', guard)
        self.assertIn("Production input or unclassified repository path changed during audit", guard)

    def test_publisher_explicitly_protects_user_managed_config(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('git diff --quiet "$GITHUB_SHA" -- modules/uu.conf', workflow)
        self.assertIn('git diff --cached --quiet "$GITHUB_SHA" -- modules/uu.conf', workflow)


    def test_audit_incidents_close_only_after_full_audit_and_publish_success(self):
        workflow = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        self.assertIn('"Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn("  resolve-audit-incidents:", workflow)
        resolver = workflow.split("  resolve-audit-incidents:", 1)[1]
        self.assertIn("github.event.workflow_run.conclusion == 'success'", resolver)
        self.assertIn("UNCLASSIFIED_STEP_FAILURE", resolver)
        self.assertIn("TEST_FAILURE", resolver)
        self.assertIn('close_issue "$issue"', resolver)
        self.assertIn('gh api --method PATCH "repos/$REPO/issues/$issue_number" -f state=closed >/dev/null', resolver)
        self.assertNotIn("gh issue close", resolver)


    def test_config_reconciliation_does_not_evaluate_rule_precedence(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Reconcile final uu.conf scope coverage after all rule mutations", workflow)
        self.assertIn("Audit candidate scope coverage against user config (read-only)", workflow)
        self.assertNotIn("uu.conf precedence", workflow)
        audit = (ROOT / "scripts" / "audit_ruleset_config_overlap.py").read_text(encoding="utf-8")
        self.assertIn("No rule order, first-match winner, or precedence is evaluated.", audit)
        sync = (ROOT / "scripts" / "sync_ruleset_config_conflicts.py").read_text(encoding="utf-8")
        self.assertIn("rule order is not evaluated", sync)


    def test_unattended_config_analysis_includes_reject_scopes_without_approving_new_rejects(self):
        audit = (ROOT / "scripts" / "audit_ruleset_config_overlap.py").read_text(encoding="utf-8")
        self.assertIn('if policy in {"DIRECT", "PROXY", "REJECT"}', audit)
        reviewer = (ROOT / "scripts" / "deterministic_review.py").read_text(encoding="utf-8")
        self.assertIn('rule.policy != "REJECT"', reviewer)
        external = (ROOT / "scripts" / "audit_external_domains.py").read_text(encoding="utf-8")
        self.assertIn('rule.policy != "REJECT"', external)

    def test_unattended_audits_do_not_resolve_config_or_ruleset_precedence(self):
        external = (ROOT / "scripts" / "audit_external_domains.py").read_text(encoding="utf-8")
        self.assertIn("scope_covers_candidate", external)
        self.assertNotIn("analyze_candidate", external)
        references = (ROOT / "scripts" / "audit_ruleset_references.py").read_text(encoding="utf-8")
        self.assertIn("cross_policy_scope_overlaps", references)
        self.assertNotIn("policy_order", references)
        self.assertNotIn("precedence_resolved_overlaps", references)


    def test_non_main_config_validation_uses_ephemeral_owner_verified_baseline(self):
        validation = (ROOT / ".github" / "workflows" / "validate-config.yml").read_text(encoding="utf-8")
        self.assertIn("Protect owner-controlled config baseline in non-main validation", validation)
        self.assertIn('git diff --quiet "$base_sha" "$head_sha" -- modules/uu.conf', validation)
        self.assertIn('for key in ("path", "approved_git_blob_sha", "last_user_approved_baseline_update")', validation)
        self.assertIn('allowed_guard_keys = {"immutable", "description", "content_immutable_to_automation", "content_protection", "baseline_metadata_policy"}', validation)
        self.assertIn("Non-main validation changed a managed-config guard field outside the semantic policy allowlist.", validation)
        self.assertNotIn('base.get("managed_config_guard") != head.get("managed_config_guard")', validation)
        self.assertIn("github.ref", validation)
        self.assertIn("github.event_name == 'pull_request'", validation)
        self.assertIn('git merge-base origin/main "$GITHUB_SHA"', validation)
        self.assertNotIn("github.event.pull_request.base.sha", validation)
        self.assertIn("BASELINE_SOURCE_EVENT", validation)
        self.assertIn("BASELINE_SOURCE_REF", validation)
        self.assertIn("BASELINE_SOURCE_SHA", validation)
        self.assertIn("python scripts/register_config_baseline.py", validation)
        self.assertIn("python scripts/verify_baseline.py --baseline-only", validation)
        self.assertIn("Audit config drift against the approved baseline", validation)


    def test_production_workflow_requires_live_fenced_resource_lease_before_publish(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("resource_lease_proof:", workflow)
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn('dispatch_task["input"]["resource_lease_proof"]', scheduler)
        self.assertIn('target_id == "workflow_auto_sync" and resource_contract is None', scheduler)
        self.assertIn("Verify live Watchdog resource lease before production audit", workflow)
        self.assertGreaterEqual(workflow.count("assert-workflow --task-id"), 2)
        self.assertIn('assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE"', workflow)
        self.assertNotIn('assert-workflow --task-id "$AUTOMATION_TASK_ID"', workflow)
        publish_start = workflow.index("      - name: Verify base commit and safely publish allowlisted outputs")
        publish_end = workflow.index("      - name: Independently verify committed remote rulesets", publish_start)
        publish_step = workflow[publish_start:publish_end]
        self.assertLess(publish_step.index("assert-workflow --task-id"), publish_step.index("git push origin HEAD:main"))
        self.assertIn("logical/production-pipeline", (ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        audit_job = workflow.split("  audit:", 1)[1].split("  publish:", 1)[0]
        self.assertNotIn("AUTOMATION_" + "WRITE_GUARD", workflow)
        self.assertNotIn("fenced_" + "file_writer", workflow)

    def test_watchdog_owns_config_change_detection_and_sync_dispatch(self):
        watchdog_path = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
        watchdog = watchdog_path.read_text(encoding="utf-8")
        production_inputs = (ROOT / "automation" / "production_inputs.json").read_text(encoding="utf-8")
        production_intent = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn('"modules/uu.conf"', watchdog)
        self.assertIn('"modules/uu.conf"', production_inputs)
        self.assertIn('INPUT_CHANGED|SCHEDULE_DUE)', watchdog)
        self.assertIn('enqueue-auto-sync', watchdog)
        self.assertIn('--revision "$ORIGIN_SHA"', watchdog)
        self.assertIn('production:input:$current_fingerprint:$current_sha', watchdog)
        self.assertIn('revision: str | None = None', production_intent)
        self.assertIn('path_classification["status"] == "INPUT_CHANGED"', production_intent)
        self.assertIn('if path in inputs:', production_intent)
        self.assertIn('"modules/uu.conf"', production_inputs)
        self.assertIn('protected_config_digest(root)', scheduler)
        self.assertIn('ensure_protected_config_unchanged', scheduler)

        # Watchdog schedules the existing production workflow; the config
        # conflict synchronizer remains a subordinate step, not an independent
        # monitor or a second workflow.
        pre_sync = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(pre_sync.count("python3 scripts/sync_ruleset_config_conflicts.py"), 2)
        self.assertIn("Remove published and queued rules that conflict with uu.conf", pre_sync)
        self.assertIn('BASELINE_SOURCE_SHA: ${{ inputs.baseline_source_sha }}', pre_sync)
        self.assertIn('(\"baseline_source_sha\", \"BASELINE_SOURCE_SHA\")', pre_sync)
        self.assertIn("does not match the durable Watchdog task input", pre_sync)
        self.assertIn("not a full Git commit SHA", pre_sync)
        self.assertIn("Reconcile final uu.conf scope coverage after all rule mutations", pre_sync)
        self.assertIn("group: shadowrocket-main-writer", pre_sync)



    def test_owner_config_registration_precedes_fingerprint_and_deterministic_tests(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        registration = workflow.index("Register repository-owner-approved uu.conf changes")
        fingerprint = workflow.index("Capture and verify the exact production input fingerprint")
        tests = workflow.index("Compile and run deterministic review tests")
        self.assertLess(registration, fingerprint)
        self.assertLess(fingerprint, tests)
        archive = workflow.split("          base_files=(", 1)[1].split("          )", 1)[0]
        self.assertNotIn("sources/policy.json", archive)
        publish = workflow.split("          publish_paths=(", 1)[1].split("          )", 1)[0]
        self.assertEqual([x.strip() for x in publish.splitlines() if x.strip()], ["rulesets/"])
        for path in ("sources/policy.json", "automation/release_manifest.json", "automation/production_workflow_map.json", "automation/resource_write_sets.json"):
            self.assertNotIn(path, publish)
        restore = (ROOT / "scripts" / "restore_automation_state.py").read_text(encoding="utf-8")
        self.assertIn("PUBLISH_FILES = set()", restore)
        self.assertIn('PUBLISH_DIR_PREFIXES = ("rulesets/",)', restore)
        self.assertNotIn('"sources/policy.json"', restore)
        registrar = (ROOT / "scripts" / "register_config_baseline.py").read_text(encoding="utf-8")
        self.assertIn("build_release_pin_updates", registrar)
        self.assertIn("write_baseline_proposal(proposal)", registrar)
        self.assertIn("RUNNER_TEMP", registrar)
        self.assertNotIn("POLICY.write_text", registrar)


    def test_manual_authorization_is_bound_to_one_durable_task_scope(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        key_position = watchdog.index('manual_key="production:manual-authorized:')
        input_position = watchdog.index("manual_input=", key_position)
        self.assertLess(key_position, input_position)
        self.assertIn("authorization_target_program_id:$target", watchdog)
        self.assertIn("authorization_idempotency_key:$idem", watchdog)

        runtime = (ROOT / "scripts" / "task_queue_runtime.py").read_text(encoding="utf-8")
        remote = (ROOT / "scripts" / "remote_task_queue_runtime.py").read_text(encoding="utf-8")
        validator = (ROOT / "scripts" / "task_queue.py").read_text(encoding="utf-8")
        self.assertIn('task.get("target_program_id") != "workflow_auto_sync"', runtime)
        self.assertIn('queue.setdefault("manual_authorizations", {})', remote)
        self.assertIn("validate_manual_authorization_consumption", remote)
        self.assertIn('manual_authorizations = queue.get("manual_authorizations", {})', validator)
        self.assertIn("manual authorization has already been consumed", runtime)


    def test_manual_watchdog_dispatch_holds_before_building_or_enqueuing_task(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        manual_gate = watchdog.index('if [ "$ORIGIN_EVENT" = "workflow_dispatch" ] && [ "${{ inputs.request_deterministic_audit }}" = "true" ]; then')
        hold_gate = watchdog.index('if [ "$manual_dispatch_mode" != "enabled" ]; then', manual_gate)
        task_key = watchdog.index('manual_key="production:manual-authorized:', manual_gate)
        enqueue = watchdog.index("enqueue-auto-sync", task_key)
        self.assertLess(manual_gate, hold_gate)
        self.assertLess(hold_gate, task_key)
        self.assertLess(task_key, enqueue)


    def test_watchdog_has_one_trusted_direct_scheduler_entry_and_disabled_canary(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        supervision_start = watchdog.index("  task-queue-supervision:")
        stale_start = watchdog.index("  stale-run-watch:", supervision_start)
        supervision = watchdog[supervision_start:stale_start]
        self.assertEqual(supervision.count("run-once"), 1)
        self.assertIn("GITHUB_ACTOR_ID: ${{ github.actor_id }}", supervision)
        self.assertIn("GITHUB_MANUAL_AUDIT_REQUEST: ${{ inputs.request_deterministic_audit }}", supervision)
        self.assertIn("GITHUB_REF_NAME: main", supervision)
        self.assertIn("GITHUB_REPOSITORY: ${{ github.repository }}", supervision)

        canary_start = watchdog.index("  assessment-canary:")
        canary_end = watchdog.index("  task-queue-supervision:", canary_start)
        canary = watchdog[canary_start:canary_end]
        self.assertIn("if: ${{ false }}", canary)


    def test_watchdog_reports_unknown_paths_without_repository_registry_writes(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        start = watchdog.index("            REVIEW_REQUIRED)")
        end = watchdog.index("            IN_PROGRESS|WAIT_FOR_ACTIVE|ALREADY_SATISFIED|OBSERVE_ONLY)", start)
        block = watchdog[start:end]
        self.assertIn("gh issue create", block)
        self.assertIn("gh issue comment", block)
        self.assertNotIn("gh api --method PUT", block)
        self.assertNotIn("register_ledger", block)
        self.assertNotIn("automation/unregistered_path_registry.json", block)
        self.assertIn("PENDING_CLASSIFICATION", watchdog)
        self.assertIn('(.path | startswith("modules/")) | not', watchdog)

    def test_watchdog_sets_scripts_path_before_importing_active_fingerprint_helper(self):
        watchdog = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        marker = 'active_fingerprints="$(CURRENT_PRODUCTION_FINGERPRINT='
        self.assertIn(marker, watchdog)
        block = watchdog.split(marker, 1)[1].split("PY\\n", 1)[0]
        self.assertIn('sys.path.insert(0, "scripts")', block)
        self.assertIn("from production_intent import active_production_fingerprints", block)

    def test_publish_step_keeps_canonical_task_id_from_revalidation(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publish = workflow.split("  publish:", 1)[1]
        step = publish.split("Verify base commit and safely publish allowlisted outputs", 1)[1].split("      - name: ", 1)[0]
        self.assertNotIn("AUTOMATION_TASK_ID:", step)

    def test_publish_revalidation_accepts_verifying_task_with_live_resource_fence(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        revalidate = workflow.split("Revalidate Watchdog task and export canonical lease context", 1)[1].split(
            "      - name: ", 1
        )[0]
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', revalidate)
        self.assertIn('task.get("status") == "CLAIMED"', revalidate)
        self.assertIn('task_lease_token = task_lease.get("token")', revalidate)
        self.assertIn('"resource-fence-only"', revalidate)
        self.assertIn('resource_lease.get("status") != "ACTIVE"', revalidate)
        self.assertIn('record.get("fencing_token") != item.get("fencing_token")', revalidate)
        self.assertIn('record.get("task_id") != task_id', revalidate)
        self.assertIn('expiry <= now', revalidate)
        self.assertNotIn('or not isinstance(lease, dict)', revalidate)


    def test_workflow_env_blocks_are_not_empty(self):
        workflow = (ROOT / ".github" / "workflows" / "auto_sync.yml").read_text(encoding="utf-8")
        lines = workflow.splitlines()
        for index, line in enumerate(lines[:-1]):
            if line.strip() != "env:":
                continue
            indent = len(line) - len(line.lstrip())
            next_line = lines[index + 1]
            next_indent = len(next_line) - len(next_line.lstrip())
            self.assertGreater(
                next_indent,
                indent,
                f"empty env mapping at line {index + 1}",
            )

if __name__ == "__main__":
    unittest.main()
