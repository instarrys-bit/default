from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import purge_legacy_source_tasks


class FakeStore:
    def __init__(self, document):
        self.document = document

    def mutate(self, callback):
        candidate, result = callback(self.document)
        self.document = candidate
        return result


def task(task_id, target, capability, status="QUEUED", attempts=0, max_attempts=1, **extra):
    value = {
        "task_id": task_id,
        "target_program_id": target,
        "capability": capability,
        "status": status,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "lease": None,
        "dispatch_intent": None,
        "state_history": [status],
        "last_error": None,
    }
    value.update(extra)
    return value


class SourceQueueRetirementTests(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "programs": [
                {"id": "script_discover_sources", "capabilities": ["source_discovery"]},
                {"id": "script_assess_sources", "capabilities": ["source_assessment"]},
            ]
        }


    def test_purge_removes_legacy_tasks_from_live_queue_and_archives_full_records(self):
        queue = {
            "schema_version": 1,
            "revision": 20,
            "tasks": [
                task("task_" + "a" * 24, "workflow_source_discovery", "source_discovery"),
                task("task_" + "b" * 24, "script_assess_sources", "source_assessment",
                     status="SUCCEEDED", attempts=1, max_attempts=1,
                     dispatch_intent={"workflow_path": ".github/workflows/source-discovery.yml"},
                     result={"dispatch_state": "submitted", "run_evidence": {"status": "completed", "conclusion": "success"}}),
                task("task_" + "d" * 24, "script_discover_sources", "source_discovery",
                     status="SUCCEEDED", attempts=1, max_attempts=1,
                     retired_target_program_id="workflow_source_discovery",
                     retirement={"schema_version": 1, "retired_target_program_id": "workflow_source_discovery",
                                 "source_discovery_mode": "monolithic_fallback"}),
                task("task_" + "c" * 24, "workflow_auto_sync", "production_audit"),
            ],
        }
        store = FakeStore(queue)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "automation").mkdir()
            (root / "automation" / "production_control.json").write_text(
                json.dumps({"schema_version": 1, "source_discovery_mode": "monolithic_fallback"}),
                encoding="utf-8",
            )
            with patch("remote_task_queue_runtime.ROOT", root), patch("remote_task_queue_runtime.validate_candidate"):
                result = purge_legacy_source_tasks(store, self.registry)
                repeated = purge_legacy_source_tasks(store, self.registry)
        self.assertEqual(result["removed_from_live_queue"], 3)
        self.assertEqual(result["archived_count"], 3)
        self.assertEqual(len(store.document["tasks"]), 1)
        self.assertEqual(len(store.document["archived_legacy_source_tasks"]), 3)
        self.assertEqual(
            sum(item.get("retired_target_program_id") == "workflow_source_discovery"
                for item in store.document["archived_legacy_source_tasks"]),
            1,
        )
        self.assertEqual(store.document["revision"], 21)
        self.assertEqual(repeated["removed_from_live_queue"], 0)
        self.assertEqual(store.document["revision"], 21)

    def test_purge_refuses_live_lease_or_unresolved_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "automation").mkdir()
            (root / "automation" / "production_control.json").write_text(
                json.dumps({"schema_version": 1, "source_discovery_mode": "monolithic_fallback"}),
                encoding="utf-8",
            )
            for extra, message in [
                ({"status": "CLAIMED", "state_history": ["QUEUED", "CLAIMED"],
                  "lease": {"owner": "worker", "token": "secret"}}, "live task state"),
                ({"dispatch_intent": {"workflow_path": ".github/workflows/source-discovery.yml"}}, "unresolved dispatch intent"),
            ]:
                queue = {"schema_version": 1, "revision": 1, "tasks": [
                    task("task_" + "d" * 24, "workflow_source_discovery", "source_discovery", **extra)
                ]}
                with patch("remote_task_queue_runtime.ROOT", root), patch("remote_task_queue_runtime.validate_candidate"):
                    with self.assertRaisesRegex(ValueError, message):
                        purge_legacy_source_tasks(FakeStore(queue), self.registry)



if __name__ == "__main__":
    unittest.main(verbosity=2)
