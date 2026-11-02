import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "auto_sync.yml"


class WorkflowConfigGuardOrderTests(unittest.TestCase):
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

    def test_publisher_explicitly_protects_user_managed_config(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('git diff --quiet "$GITHUB_SHA" -- shadowrocket/ss.conf', workflow)
        self.assertIn('git diff --cached --quiet "$GITHUB_SHA" -- shadowrocket/ss.conf', workflow)


if __name__ == "__main__":
    unittest.main()
