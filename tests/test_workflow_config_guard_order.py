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
        self.assertIn("cancel-in-progress: true", workflow)
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
        final = workflow.index("Enforce final ss.conf precedence after all rule mutations")
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


if __name__ == "__main__":
    unittest.main()
