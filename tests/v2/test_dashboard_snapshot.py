import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))
from dashboard_snapshot import build_snapshot
from runtime import empty_state, append_event


class DashboardSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.migration = {
            "source_archive": {"commit":"c" * 40, "tree_sha":"d" * 40},
            "entries": [
                {"migration_status":"DISCOVERED_NOT_IMPORTED","promotion_status":"QUARANTINED_PENDING_VALIDATION"},
                {"migration_status":"DISCOVERED_NOT_IMPORTED","promotion_status":"QUARANTINED_PENDING_VALIDATION"},
            ],
        }
        self.inventory = {"file_count":239,"total_bytes":280466056,"tree_sha":"d" * 40}

    def test_uninitialized_epoch_is_reported_without_fabricating_queue_state(self):
        result = build_snapshot(None, self.migration, self.inventory)
        self.assertEqual(result["epoch"]["status"], "NOT_INITIALIZED")
        self.assertIsNone(result["epoch"]["revision"])
        self.assertEqual(result["tasks"]["total"], 0)
        self.assertEqual(result["resources"]["total"], 0)
        self.assertEqual(result["migration"]["candidate_count"], 2)
        self.assertEqual(result["migration"]["imported_count"], 0)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["safety"]["production_cutover"])

    def test_initialized_epoch_uses_event_projection_and_redacts_lease_tokens(self):
        state = empty_state("epoch-test")
        state, _ = append_event(state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task_test","max_attempts":2}, actor="watchdog",
            idempotency_key="enqueue-1", expected_revision=0,
            created_at="2026-11-17T00:00:00Z")
        state, _ = append_event(state, event_type="TASK_CLAIMED",
            payload={"task_id":"task_test","lease_id":"lease-1","owner":"worker","token":"secret-token","expires_at":"2026-11-17T00:10:00Z"},
            actor="watchdog", idempotency_key="claim-1", expected_revision=1,
            created_at="2026-11-17T00:01:00Z")
        result = build_snapshot(state, self.migration, self.inventory)
        self.assertEqual(result["epoch"]["revision"], 2)
        self.assertEqual(result["tasks"]["status_counts"], {"CLAIMED":1})
        self.assertEqual(result["resources"]["total"], 0)
        self.assertNotIn("secret-token", str(result))
        self.assertNotIn("lease-1", str(result))
        self.assertTrue(result["read_only"])


    def test_v2_dashboard_page_has_no_mutation_controls(self):
        page = (ROOT / "dashboard/v2/index.html").read_text(encoding="utf-8")
        lower = page.lower()
        self.assertIn("只读", page)
        self.assertIn('fetch("./data.json', page)
        self.assertNotIn("<form", lower)
        self.assertNotIn('method="post"', lower)
        self.assertNotIn("xmlhttprequest", lower)
        self.assertNotIn("storage/v2/state.json", page)

    def test_pages_workflow_uses_only_read_permission_for_snapshot(self):
        workflow = (ROOT / ".github/workflows/dashboard-pages.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("storage/v2/dashboard_snapshot.py", workflow)


if __name__ == "__main__":
    unittest.main()
