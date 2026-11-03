import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "auto_sync.yml"


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
        self.assertIn('Refusing to spend resources on stale review inputs.', workflow)
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

    def test_every_main_writer_uses_the_shared_repository_lock(self):
        auto_sync = WORKFLOW.read_text(encoding="utf-8")
        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-main-writer", auto_sync)
        self.assertIn("group: shadowrocket-main-writer", intake)
        manifest_writer = watchdog.split("  manifest-integrity:", 1)[1]
        self.assertIn("group: shadowrocket-main-writer", manifest_writer)
        self.assertNotIn("github-only-domain-intake", intake)

    def test_request_intake_retries_non_fast_forward_without_force_push(self):
        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        self.assertIn("for attempt in 1 2 3; do", intake)
        self.assertIn("git fetch origin main", intake)
        self.assertIn("git rebase origin/main", intake)
        self.assertIn("git push origin HEAD:main", intake)
        self.assertNotIn("git push --force", intake)

    def test_self_healing_never_cancels_non_main_runs_or_cross_closes_incidents(self):
        healing = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('if run.get("head_branch") != "main":', watchdog)
        self.assertNotIn("gh run cancel", healing)
        self.assertIn('select(.head_branch == "main" and .id > $failed)', healing)
        self.assertIn("workflow=deterministic_audit;run_id=", healing)
        self.assertIn("workflow=config_validator;run_id=", healing)
        self.assertIn('workflow_key="config_validator"', healing)
        self.assertIn('workflow_key="deterministic_audit"', healing)
        self.assertIn('title="Self-healing incident: $classification ($workflow_key; ${FAILED_SHA:0:8})"', healing)
        self.assertIn('title="Self-healing agent failure: $workflow_key (source run $SOURCE_RUN_ID)"', healing)

    def test_automation_incidents_are_bound_to_exact_workflow_runs(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Shadowrocket automation failure (run $RUN_ID)", workflow)
        self.assertIn("workflow=auto_sync;run_id=$RUN_ID", workflow)
        self.assertIn("capture(\"shadowrocket-automation:workflow=auto_sync;run_id=", workflow)
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
        self.assertIn('tar -czf audit-output.tar.gz -- "${archive_inputs[@]}"', package)
        self.assertIn("data/domain_candidates.json", package)

    def test_large_state_is_artifact_backed_not_committed_as_giant_json(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publish = workflow.split("      - name: Verify base commit and safely publish allowlisted outputs", 1)[1]
        allowlist = publish.split("          publish_paths=(", 1)[1].split("          )", 1)[0]
        for path in ("sources/domain_reviews.json", "sources/review_cursor.json",
                     "sources/rule_provenance.json", "data/domain_candidates.json",
                     "data/candidates.json", "data/source_pending.json", "data/source_snapshots/"):
            self.assertNotIn(path, allowlist)
        self.assertIn("reports/automation/state_store.json", allowlist)
        self.assertIn('if [[ -e "$path" ]]', publish)
        self.assertIn('git add -- "$path"', publish)

    def test_config_conflicts_are_checked_before_and_after_rule_mutations(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        pre = workflow.index("Remove published and queued rules that conflict with ss.conf")
        collect = workflow.index("Collect and cross-check all enabled domain sources")
        build = workflow.index("Build standalone DIRECT, PROXY and REJECT rule sets")
        lifecycle = workflow.index("Run conservative lifecycle audit and selectable restoration")
        final = workflow.index("Reconcile final ss.conf scope coverage after all rule mutations")
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
        self.assertIn("Non-documentation input or repository state changed during audit", guard)

    def test_publisher_explicitly_protects_user_managed_config(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('git diff --quiet "$GITHUB_SHA" -- shadowrocket/ss.conf', workflow)
        self.assertIn('git diff --cached --quiet "$GITHUB_SHA" -- shadowrocket/ss.conf', workflow)


    def test_audit_incidents_close_only_after_full_audit_and_publish_success(self):
        workflow = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        self.assertIn('"Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn("  resolve-audit-incidents:", workflow)
        resolver = workflow.split("  resolve-audit-incidents:", 1)[1]
        self.assertIn("github.event.workflow_run.conclusion == 'success'", resolver)
        self.assertIn("UNCLASSIFIED_STEP_FAILURE", resolver)
        self.assertIn("TEST_FAILURE", resolver)
        self.assertIn("gh issue close", resolver)


    def test_config_reconciliation_does_not_evaluate_rule_precedence(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Reconcile final ss.conf scope coverage after all rule mutations", workflow)
        self.assertIn("Audit candidate scope coverage against user config (read-only)", workflow)
        self.assertNotIn("ss.conf precedence", workflow)
        audit = (ROOT / "scripts" / "audit_ruleset_config_overlap.py").read_text(encoding="utf-8")
        self.assertIn("No rule order, first-match winner, or precedence is evaluated.", audit)
        sync = (ROOT / "scripts" / "sync_ruleset_config_conflicts.py").read_text(encoding="utf-8")
        self.assertIn("rule order is not evaluated", sync)


    def test_unattended_config_analysis_excludes_reject_decisions(self):
        audit = (ROOT / "scripts" / "audit_ruleset_config_overlap.py").read_text(encoding="utf-8")
        self.assertIn('if policy in {"DIRECT", "PROXY"}', audit)
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


if __name__ == "__main__":
    unittest.main()
