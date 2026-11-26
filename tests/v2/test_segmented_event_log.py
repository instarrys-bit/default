import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from runtime import append_event, empty_state
from segmented_event_log import (
    SEGMENT_ROOT, append_segmented_event, build_segmented_state,
    verify_segmented_state,
)


class SegmentedEventLogTests(unittest.TestCase):
    def _state(self, count):
        state = empty_state("segmented-test")
        for index in range(count):
            state, _ = append_event(
                state,
                event_type="TASK_ENQUEUED",
                payload={"task_id": f"task-{index}", "max_attempts": 2},
                actor="test",
                idempotency_key=f"enqueue-{index}",
                expected_revision=state["revision"],
                created_at="2026-11-26T00:00:00Z",
            )
        return state

    def test_build_and_verify_segments(self):
        state = self._state(8)
        manifest, payloads = build_segmented_state(state, max_segment_bytes=400)
        self.assertGreater(manifest["segment_count"], 1)
        restored = verify_segmented_state(manifest, payloads, max_segment_bytes=400)
        self.assertEqual(restored, state)
        self.assertEqual(manifest["total_event_count"], 8)

    def test_append_extends_tail_without_losing_history(self):
        state = self._state(2)
        manifest, payloads = build_segmented_state(state, max_segment_bytes=1200)
        next_state, _ = append_event(
            state, event_type="TASK_ENQUEUED",
            payload={"task_id": "task-2", "max_attempts": 2},
            actor="test", idempotency_key="enqueue-2",
            expected_revision=state["revision"],
            created_at="2026-11-26T00:00:01Z",
        )
        new_manifest, new_payloads = append_segmented_event(
            manifest, payloads, next_state, max_segment_bytes=1200
        )
        self.assertEqual(new_manifest["total_event_count"], 3)
        self.assertEqual(verify_segmented_state(new_manifest, new_payloads, max_segment_bytes=1200), next_state)

    def test_append_rolls_to_new_segment_when_tail_is_full(self):
        state = self._state(2)
        manifest, payloads = build_segmented_state(state, max_segment_bytes=700)
        next_state, _ = append_event(
            state, event_type="TASK_ENQUEUED",
            payload={"task_id": "task-2", "max_attempts": 2},
            actor="test", idempotency_key="enqueue-2",
            expected_revision=state["revision"],
            created_at="2026-11-26T00:00:01Z",
        )
        new_manifest, new_payloads = append_segmented_event(
            manifest, payloads, next_state, max_segment_bytes=700
        )
        self.assertEqual(new_manifest["segment_count"], manifest["segment_count"] + 1)
        self.assertEqual(verify_segmented_state(new_manifest, new_payloads, max_segment_bytes=700), next_state)

    def test_detects_segment_tampering(self):
        manifest, payloads = build_segmented_state(self._state(2), max_segment_bytes=1200)
        broken = dict(payloads)
        path = next(iter(broken))
        broken[path] += b"{}\n"
        with self.assertRaisesRegex(ValueError, "byte count or SHA-256"):
            verify_segmented_state(manifest, broken, max_segment_bytes=1200)

    def test_detects_manifest_tampering(self):
        manifest, payloads = build_segmented_state(self._state(2), max_segment_bytes=1200)
        broken = copy.deepcopy(manifest)
        broken["total_event_count"] += 1
        with self.assertRaisesRegex(ValueError, "manifest SHA-256"):
            verify_segmented_state(broken, payloads, max_segment_bytes=1200)

    def test_rejects_missing_or_extra_segments(self):
        manifest, payloads = build_segmented_state(self._state(3), max_segment_bytes=700)
        broken = dict(payloads)
        broken.pop(next(iter(broken)))
        with self.assertRaisesRegex(ValueError, "payload set"):
            verify_segmented_state(manifest, broken, max_segment_bytes=700)

    def test_rejects_event_state_that_rewrites_history(self):
        state = self._state(2)
        manifest, payloads = build_segmented_state(state, max_segment_bytes=1200)
        tampered = copy.deepcopy(state)
        tampered["events"][0]["payload"]["task_id"] = "rewritten"
        with self.assertRaises(ValueError):
            append_segmented_event(manifest, payloads, tampered, max_segment_bytes=1200)


if __name__ == "__main__":
    unittest.main()
