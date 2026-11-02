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
        self.assertIn('current_main="$(gh api "repos/$REPO/commits/main" --jq .sha)"', workflow)
        self.assertIn('Stopping before source discovery.', workflow)
        self.assertIn('Refusing to spend resources on stale review inputs.', workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("Keep the active audit; stale-commit guards stop obsolete runs safely.", workflow)
        self.assertIn("group: shadowrocket-main-writer", workflow)
        self.assertIn("Independently verify committed remote rulesets", workflow)
        self.assertLess(workflow.index("git push origin HEAD:main"), workflow.index("Independently verify committed remote rulesets"))

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
        package = workflow.split("tar -czf audit-output.tar.gz", 1)[1].split(
            "      - name: Upload allowlisted audit outputs", 1
        )[0]
        self.assertIn("reports/automation/state_store.json", package)

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
        resolver = workflow.split("  resolve-audit-incidents:", 1)[1].split("  stale-run-watch:", 1)[0]
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
