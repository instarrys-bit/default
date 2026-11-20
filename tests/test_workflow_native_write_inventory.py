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

    def test_scan_covers_every_registered_workflow_file(self):
        inventory = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["workflow_native_scan"]["workflow_count"], len(WORKFLOWS))
        self.assertTrue(all(site["workflow_path"] in WORKFLOWS for site in self.sites))

    def test_exactly_four_workflow_files_exist(self):
        root = ROOT / ".github/workflows"
        actual = sorted(p.name for p in root.glob("*.yml"))
        self.assertEqual(actual, [
            "auto_sync.yml",
            "automation-watchdog.yml",
            "dashboard-pages.yml",
            "storage-management.yml",
        ])

    def test_watchdog_health_check_can_write_queue(self):
        watchdog = (ROOT / ".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        # Queue CAS requires contents write on the job that calls enqueue-auto-sync.
        self.assertIn("enqueue-auto-sync", watchdog)
        self.assertIn("contents: write", watchdog)
        self.assertIn("task-queue-supervision", watchdog)

    def test_auto_sync_publisher_mutex_group(self):
        auto_sync = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertRegex(auto_sync, r"(?m)^  group: shadowrocket-main-writer$")
        self.assertRegex(auto_sync, r"(?m)^  cancel-in-progress: false$")


if __name__ == "__main__":
    unittest.main()
