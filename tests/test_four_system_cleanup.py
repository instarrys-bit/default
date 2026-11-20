from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FourSystemCleanupTests(unittest.TestCase):
    def test_completed_legacy_workflows_and_queue_pointer_are_retired(self):
        retired = [
            ".github/workflows/migrate-queue-to-repo-json.yml",
            ".github/workflows/v2-watchdog-supervisor.yml",
            ".github/workflows/queue-lease-recovery.yml",
            ".github/workflows/restore-queue-store.yml",
            "automation/queue_store_pointer.json",
        ]
        for relative in retired:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists(), relative)

    def test_queue_store_uses_repository_contents_api_only(self):
        source = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        self.assertIn("/contents/", source)
        self.assertNotIn("issue_number", source)
        self.assertNotIn("/issues/", source)
        self.assertNotIn("resolve_queue_issue_number", source)

    def test_production_request_observations_are_checked_in_only(self):
        source = (ROOT / "scripts/production_intent.py").read_text(encoding="utf-8")
        self.assertIn("sources/request_domain_observations.json", source)
        self.assertNotIn("REQUEST_OBSERVATION_ISSUE_NUMBER", source)
        self.assertNotIn("/issues/", source)
        self.assertNotIn("urlopen", source)

    def test_all_active_workflows_are_issue_api_free(self):
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(workflows)
        for path in workflows:
            content = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotRegex(content, r"(?m)^\s*issues:\s*(?:read|write)\s*$")
                self.assertNotIn("gh issue", content)
                self.assertNotIn("/issues/", content)

    def test_storage_management_owns_incident_and_queue_state_paths(self):
        store = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        incident = (ROOT / "storage" / "v2" / "incident_store.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        self.assertIn('"automation/task_queue.json"', store)
        self.assertIn('"storage/v2/incidents.json"', store)
        self.assertIn("path not in ALLOWED_STATE_PATHS", store)
        self.assertIn("storage/v2/incidents.json", incident)
        self.assertIn("contents: write", workflow)
        self.assertIn("automation_task_id:", workflow)
        self.assertFalse((ROOT / ".github" / "workflows" / "storage-incident-management.yml").exists())
        self.assertNotIn("gh issue", workflow)

    def test_runtime_python_has_no_github_issues_transport(self):
        paths = list((ROOT / "scripts").glob("*.py")) + list((ROOT / "storage" / "v2").glob("*.py"))
        for path in paths:
            content = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("/issues/", content)
                self.assertNotIn("gh issue", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
