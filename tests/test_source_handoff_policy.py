import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from source_handoff_policy import (
    DISCOVERY_PIPELINE_REVISION_PATHS,
    classify_assessment_handoff,
    discovery_pipeline_revision,
    discovery_task_requires_handoff,
)


def assessment_task(task_id, run_id, status="SUCCEEDED", key=None, verified=True, created_at="2026-11-07T12:00:00Z"):
    return {
        "task_id": task_id,
        "target_program_id": "script_assess_sources",
        "idempotency_key": key or f"source-assessment:{run_id}",
        "created_at": created_at,
        "status": status,
        "input": {"predecessor": {"workflow_run_id": run_id}},
        "verification": {"status": "passed" if verified else "failed"},
        "result": {
            "artifact_verification": {
                "valid": verified,
                "activation_count": 0 if verified else 1,
            }
        },
    }


def discovery_task(run_id="42373818238", status="SUCCEEDED", include_run_evidence=True):
    result = {"run_evidence": {"run_id": run_id}} if include_run_evidence else {}
    return {
        "task_id": "task_discovery",
        "target_program_id": "workflow_source_discovery",
        "status": status,
        "result": result,
    }


class SourceHandoffPolicyTests(unittest.TestCase):
    def test_verified_assessment_releases_terminal_discovery_for_next_cycle(self):
        discovery = discovery_task()
        assessment = assessment_task("task_assessed", "42373818238")
        self.assertFalse(discovery_task_requires_handoff(discovery, [discovery, assessment]))

    def test_newer_verified_discovery_supersedes_older_unassessed_run(self):
        older = discovery_task(run_id="42373818238")
        older["created_at"] = "2026-11-07T12:00:00Z"
        newer = discovery_task(run_id="42417075148")
        newer["task_id"] = "task_discovery_newer"
        newer["created_at"] = "2026-11-08T12:00:00Z"
        assessment = assessment_task("task_newer_assessed", "42417075148")
        self.assertFalse(discovery_task_requires_handoff(older, [older, newer, assessment]))

    def test_newer_discovery_without_verified_assessment_does_not_supersede(self):
        older = discovery_task(run_id="42373818238")
        older["created_at"] = "2026-11-07T12:00:00Z"
        newer = discovery_task(run_id="42417075148")
        newer["task_id"] = "task_discovery_newer"
        newer["created_at"] = "2026-11-08T12:00:00Z"
        self.assertTrue(discovery_task_requires_handoff(older, [older, newer]))

    def test_succeeded_discovery_without_verified_assessment_still_needs_handoff(self):
        discovery = discovery_task()
        self.assertTrue(discovery_task_requires_handoff(discovery, [discovery]))

    def test_active_assessment_keeps_discovery_handoff_blocked(self):
        discovery = discovery_task()
        assessment = assessment_task("task_active", "42373818238", status="QUEUED", verified=False)
        self.assertTrue(discovery_task_requires_handoff(discovery, [discovery, assessment]))

    def test_invalid_assessment_evidence_keeps_discovery_visible(self):
        discovery = discovery_task()
        assessment = assessment_task("task_invalid", "42373818238", verified=False)
        self.assertTrue(discovery_task_requires_handoff(discovery, [discovery, assessment]))

    def test_missing_discovery_run_evidence_remains_pending_for_exact_resolution(self):
        discovery = discovery_task(include_run_evidence=False)
        assessment = assessment_task("task_assessed", "42373818238")
        self.assertTrue(discovery_task_requires_handoff(discovery, [discovery, assessment]))

    def test_nonterminal_discovery_is_not_released_by_old_assessment(self):
        discovery = discovery_task(status="VERIFYING")
        assessment = assessment_task("task_assessed", "42373818238")
        self.assertTrue(discovery_task_requires_handoff(discovery, [discovery, assessment]))

    def test_no_existing_assessment_is_ready(self):
        result = classify_assessment_handoff([], "42373818238")
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["task_ids"], [])

    def test_legacy_and_versioned_keys_for_same_run_are_deduplicated(self):
        tasks = [
            assessment_task("task_legacy", "42373818238", key="source-assessment:42373818238"),
            assessment_task("task_versioned", "42373818238", key="source-assessment:42373818238:parser-v2",
                            created_at="2026-11-07T13:00:00Z"),
        ]
        result = classify_assessment_handoff(tasks, "42373818238")
        self.assertEqual(result["state"], "already_assessed")
        self.assertEqual(result["canonical_task_id"], "task_legacy")
        self.assertEqual(result["duplicate_task_ids"], ["task_versioned"])

    def test_predecessor_identity_deduplicates_even_when_keys_differ(self):
        tasks = [
            assessment_task("task_a", "42373818238", key="assessment:old-format"),
            assessment_task("task_b", "42373818238", key="assessment:new-format"),
        ]
        result = classify_assessment_handoff(tasks, "42373818238")
        self.assertEqual(result["state"], "already_assessed")
        self.assertEqual(result["task_ids"], ["task_a", "task_b"])

    def test_active_assessment_prevents_replacement_discovery_and_duplicate_enqueue(self):
        task = assessment_task("task_active", "42373818238", status="QUEUED", verified=False)
        result = classify_assessment_handoff([task], "42373818238")
        self.assertEqual(result["state"], "assessment_pending")
        self.assertEqual(result["canonical_task_id"], "task_active")

    def test_dead_letter_assessment_is_recovery_required_not_a_new_discovery(self):
        task = assessment_task("task_dead", "42373818238", status="DEAD_LETTER", verified=False)
        result = classify_assessment_handoff([task], "42373818238")
        self.assertEqual(result["state"], "assessment_retry_required")

    def test_succeeded_task_requires_independent_verification_and_non_activation(self):
        invalid = assessment_task("task_invalid", "42373818238", verified=False)
        result = classify_assessment_handoff([invalid], "42373818238")
        self.assertEqual(result["state"], "assessment_evidence_invalid")

    def test_idempotency_prefix_match_is_delimiter_bounded(self):
        other = assessment_task("task_other", "42373818239", key="source-assessment:42373818239")
        result = classify_assessment_handoff([other], "4237381823")
        self.assertEqual(result["state"], "ready")

    def test_pipeline_revision_changes_when_handoff_or_queue_code_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in DISCOVERY_PIPELINE_REVISION_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("baseline", encoding="utf-8")
            before = discovery_pipeline_revision(root)
            (root / "scripts/task_scheduler.py").write_text("changed scheduler", encoding="utf-8")
            self.assertNotEqual(before, discovery_pipeline_revision(root))

    def test_pipeline_revision_ignores_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in DISCOVERY_PIPELINE_REVISION_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("baseline", encoding="utf-8")
            before = discovery_pipeline_revision(root)
            (root / "README.md").write_text("unrelated", encoding="utf-8")
            self.assertEqual(before, discovery_pipeline_revision(root))

    def test_pipeline_revision_fails_closed_when_a_component_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                discovery_pipeline_revision(Path(directory))

    def test_pipeline_revision_changes_when_watchdog_or_assessor_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in DISCOVERY_PIPELINE_REVISION_PATHS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("baseline", encoding="utf-8")
            before = discovery_pipeline_revision(root)
            for relative in (".github/workflows/automation-watchdog.yml", "scripts/assess_sources.py"):
                path = root / relative
                path.write_text("changed", encoding="utf-8")
                self.assertNotEqual(before, discovery_pipeline_revision(root))
                path.write_text("baseline", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
