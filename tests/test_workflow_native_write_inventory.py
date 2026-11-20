import re
import unittest
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ".github/workflows/auto_sync.yml",
    ".github/workflows/automation-watchdog.yml",
    ".github/workflows/dashboard-pages.yml",
    ".github/workflows/storage-management.yml",
]
PATTERNS = {
    "git_add": re.compile(r"\bgit\s+add\b"),
    "git_commit": re.compile(r"\bgit\s+commit\b"),
    "git_push": re.compile(r"\bgit\s+push\b"),
    "git_reset": re.compile(r"\bgit\s+reset\b"),
    "git_checkout": re.compile(r"\bgit\s+checkout\b"),
    "github_contents_put": re.compile(r"\bgh\s+api\b.*--method\s+PUT", re.I),
    "github_contents_delete": re.compile(r"\bgh\s+api\b.*--method\s+DELETE", re.I),
    "github_issue_patch": re.compile(r"\bgh\s+api\b.*--method\s+PATCH", re.I),
    "github_issue_comment_post": re.compile(r"\bgh\s+api\b.*--method\s+POST", re.I),
    "workflow_dispatch": re.compile(r"\bgh\s+workflow\s+run\b"),
    "workflow_dispatch_api": re.compile(r"actions/workflows/[A-Za-z0-9_.-]+/dispatches"),
}


class WorkflowNativeWriteInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
        cls.sites = cls.inventory["workflow_native_write_sites"]
        cls.by_key = {(x["workflow_path"], x["step_name"]): x for x in cls.sites}

    def test_all_shell_git_and_github_api_mutation_steps_are_inventoried(self):
        discovered = set()
        for workflow in WORKFLOWS:
            lines = (ROOT / workflow).read_text(encoding="utf-8").splitlines()
            step_name = "(workflow preamble)"
            for line in lines:
                match = re.match(r"^\s*- name:\s*(.*)$", line)
                if match:
                    step_name = match.group(1).strip().strip("\\\"'")
                kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(line)]
                if kinds:
                    key = (workflow, step_name)
                    discovered.add(key)
                    self.assertIn(key, self.by_key, f"unclassified workflow mutation step: {workflow} / {step_name}")
                    declared = set(self.by_key[key]["mutation_kinds"])
                    for kind in kinds:
                        self.assertIn(kind, declared, f"{kind} missing from inventory for {workflow} / {step_name}")
        declared_shell_sites = {
            key for key, site in self.by_key.items()
            if any(kind in PATTERNS for kind in site["mutation_kinds"])
        }
        self.assertEqual(declared_shell_sites, discovered)

    def test_watchdog_repository_writes_are_limited_to_rulesets(self):
        watchdog = (ROOT / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertNotIn("baseline-sync:", watchdog)
        self.assertNotIn("Apply owner-verified metadata-only baseline synchronization", watchdog)
        mutations = [
            line.strip()
            for line in watchdog.splitlines()
            if re.search(r"\bgit\s+(?:add|commit|push)\b", line)
        ]
        self.assertEqual(mutations, [
            "git add -- rulesets/manifest.json",
            'git commit -m "Reconcile published RULE-SET manifest metadata"',
            "git push origin HEAD:main",
        ])
        queue_job = watchdog.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("      contents: write", queue_job)
        self.assertIn("storage/v2/queue_store.py", (ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        self.assertNotIn("git push", queue_job)
        self.assertIn("      contents: write", watchdog.split("  manifest-integrity:", 1)[1])

    def test_watchdog_artifact_recovery_uses_reviewed_four_url_budget(self):
        watchdog = (ROOT / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("'{max_urls:4,max_file_bytes:1000000,max_total_bytes:10000000,predecessor:$predecessor}'", watchdog)

    def test_scan_covers_every_registered_workflow_file(self):
        inventory = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["workflow_native_scan"]["workflow_count"], len(WORKFLOWS))
        self.assertTrue(all(site["workflow_path"] in WORKFLOWS for site in self.sites))

    def test_watchdog_manifest_writer_serializes_with_auto_sync(self):
        watchdog = (ROOT / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        auto_sync = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertRegex(
            watchdog,
            r"(?ms)^  manifest-integrity:\n(?:(?!^  [A-Za-z0-9_-]+:).)*?^    concurrency:\n      group: shadowrocket-main-writer\n      cancel-in-progress: false",
        )
        self.assertRegex(auto_sync, r"(?m)^  group: shadowrocket-main-writer$")
        self.assertRegex(auto_sync, r"(?m)^  cancel-in-progress: false$")

    def test_each_workflow_native_side_effect_has_resource_and_boundary_evidence(self):
        for site in self.sites:
            with self.subTest(workflow=site["workflow_path"], step=site["step_name"]):
                self.assertTrue(site["mutation_kinds"])
                self.assertTrue(site["resources"])
                self.assertTrue(site["fence"])
                self.assertTrue(site["boundary"])
        pages = next(x for x in self.sites if "github_pages_deployment" in x["mutation_kinds"])
        workflow = (ROOT / pages["workflow_path"]).read_text(encoding="utf-8")
        self.assertIn("actions/deploy-pages", workflow)


if __name__ == "__main__":
    unittest.main()
