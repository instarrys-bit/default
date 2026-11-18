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
            "automation/queue_store_pointer.json",
        ]
        for relative in retired:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists(), relative)

    def test_queue_store_uses_repository_contents_api_only(self):
        source = (ROOT / "scripts/github_queue_store.py").read_text(encoding="utf-8")
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

    def test_non_issue_workflows_do_not_request_issue_permissions(self):
        paths = [
            ".github/workflows/source-discovery.yml",
            ".github/workflows/queue-snapshot-artifact.yml",
            ".github/workflows/dashboard-pages.yml",
            ".github/workflows/queue-lease-recovery.yml",
        ]
        for relative in paths:
            content = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertIsNone(
                    re.search(r"(?m)^\s*issues:\s*(?:read|write)\s*$", content),
                    f"{relative} requests an unnecessary GitHub Issues permission",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
