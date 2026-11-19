from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import retire_legacy_source_tasks


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

    def test_retires_queued_tasks_and_preserves_terminal_history(self):
        queue = {
            "schema_version": 1,
            "revision": 10,
            "tasks": [
                task("task_" + "a" * 24, "workflow_source_discovery", "source_discovery"),
                task("task_" + "b" * 24, "workflow_source_discovery", "source_discovery",
                     status="SUCCEEDED", attempts=1, max_attempts=1),
                task("task_" + "c" * 24, "script_assess_sources", "source_assessment"),
                task("task_" + "d" * 24, "script_assess_sources", "source_assessment",
                     status="DEAD_LETTER", attempts=1, max_attempts=1),
            ],
        }
        store = FakeStore(queue)
        with patch("remote_task_queue_runtime.validate_candidate"):
            result = retire_legacy_source_tasks(store, self.registry)

        by_id = {item["task_id"]: item for item in store.document["tasks"]}
        discovery_queued = by_id["task_" + "a" * 24]
        discovery_succeeded = by_id["task_" + "b" * 24]
        assessment_queued = by_id["task_" + "c" * 24]
        assessment_dead = by_id["task_" + "d" * 24]

        self.assertEqual(result["changed_count"], 4)
        self.assertEqual(result["cancelled_count"], 2)
        self.assertEqual(store.document["revision"], 11)
        self.assertEqual(discovery_queued["target_program_id"], "script_discover_sources")
        self.assertEqual(discovery_queued["status"], "CANCELLED")
        self.assertEqual(discovery_succeeded["target_program_id"], "script_discover_sources")
        self.assertEqual(discovery_succeeded["status"], "SUCCEEDED")
        self.assertEqual(assessment_queued["status"], "CANCELLED")
        self.assertEqual(assessment_dead["status"], "DEAD_LETTER")
        self.assertEqual(discovery_queued["retirement"]["source_discovery_mode"], "monolithic_fallback")

        with patch("remote_task_queue_runtime.validate_candidate"):
            repeated = retire_legacy_source_tasks(store, self.registry)
        self.assertEqual(repeated["changed_count"], 0)
        self.assertEqual(store.document["revision"], 11)

    def test_refuses_to_cancel_a_live_task_or_unresolved_dispatch(self):
        live = {
            "schema_version": 1,
            "revision": 1,
            "tasks": [
                task("task_" + "e" * 24, "workflow_source_discovery", "source_discovery",
                     status="CLAIMED", state_history=["QUEUED", "CLAIMED"], lease={"owner": "worker", "token": "secret"}),
            ],
        }
        store = FakeStore(live)
        with patch("remote_task_queue_runtime.validate_candidate"):
            with self.assertRaisesRegex(ValueError, "live task state"):
                retire_legacy_source_tasks(store, self.registry)

        pending = {
            "schema_version": 1,
            "revision": 1,
            "tasks": [
                task("task_" + "f" * 24, "workflow_source_discovery", "source_discovery",
                     dispatch_intent={"workflow_path": ".github/workflows/source-discovery.yml"}),
            ],
        }
        store = FakeStore(pending)
        with patch("remote_task_queue_runtime.validate_candidate"):
            with self.assertRaisesRegex(ValueError, "unresolved dispatch intent"):
                retire_legacy_source_tasks(store, self.registry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
