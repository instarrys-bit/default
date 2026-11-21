import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from source_handoff_policy import (DISCOVERY_PIPELINE_REVISION_PATHS, classify_assessment_handoff, latest_verified_assessed_discovery, discovery_pipeline_revision, discovery_task_requires_handoff, select_source_worker_task, select_production_worker_task)


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
        "verification": {"status": "passed"},
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


    def test_artifact_recovery_is_selected_after_assessment_gate_opens(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        recovery = assessment_task(
            "task_artifact_recovery",
            "42417075148",
            status="QUEUED",
            verified=False,
            key="source-assessment:42417075148:parser-v2:artifact-recovery:1",
            created_at="2026-11-07T14:00:00Z",
        )
        self.assertEqual(
            select_source_worker_task([discovery, assessment, recovery], predecessor_workflow_run_id="42417075148"),
            "task_artifact_recovery",
        )

    def test_queued_assessment_precedes_next_queued_discovery(self):
        discovery = discovery_task(run_id="42417075149", status="QUEUED")
        discovery["priority"] = 100
        assessment = assessment_task(
            "task_assessment_pending",
            "42417075148",
            status="QUEUED",
            verified=False,
        )
        assessment["priority"] = 1
        self.assertEqual(
            select_source_worker_task([discovery, assessment], predecessor_workflow_run_id="42417075148"),
            "task_assessment_pending",
        )

    def test_verified_assessment_gate_blocks_other_work_without_artifact_recovery(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        unrelated = {
            "task_id": "task_unrelated",
            "target_program_id": "script_other",
            "status": "QUEUED",
            "priority": 100,
        }
        self.assertEqual(select_source_worker_task([discovery, assessment, unrelated], predecessor_workflow_run_id="42417075148"), "")



    def test_assessment_selection_is_scoped_to_exact_discovery_predecessor(self):
        discovery = discovery_task(run_id="42939875322")
        older = assessment_task("task_assessment_old", "42931914274", status="QUEUED", verified=False)
        current = assessment_task("task_assessment_current", "42939875322", status="QUEUED", verified=False)
        tasks = [discovery, older, current]
        self.assertEqual(
            select_source_worker_task(tasks, predecessor_workflow_run_id="42939875322"),
            "task_assessment_current",
        )
        self.assertEqual(select_source_worker_task(tasks), "")

    def test_artifact_recovery_is_scoped_to_exact_discovery_predecessor(self):
        discovery = discovery_task(run_id="42939875322")
        old_recovery = assessment_task(
            "task_old_recovery", "42931914274", status="QUEUED", verified=False,
            key="source-assessment:42931914274:parser-v2:artifact-recovery:1",
        )
        current_assessment = assessment_task("task_current_assessment", "42939875322")
        current_recovery = assessment_task(
            "task_current_recovery", "42939875322", status="QUEUED", verified=False,
            key="source-assessment:42939875322:parser-v2:artifact-recovery:1",
        )
        self.assertEqual(
            select_source_worker_task(
                [discovery, old_recovery, current_assessment, current_recovery],
                predecessor_workflow_run_id="42939875322",
            ),
            "task_current_recovery",
        )

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



    def test_newer_unassessed_discovery_does_not_block_existing_verified_snapshot(self):
        older = discovery_task(run_id="42373818238")
        older["created_at"] = "2026-11-07T12:00:00Z"
        older_assessment = assessment_task("task_older_assessed", "42373818238")
        newer = discovery_task(run_id="42417075148", status="VERIFYING")
        newer["task_id"] = "task_discovery_newer"
        newer["created_at"] = "2026-11-08T12:00:00Z"
        self.assertEqual(
            latest_verified_assessed_discovery([older, older_assessment, newer])["task_id"],
            "task_discovery",
        )
        production = {
            "task_id": "task_production",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "input": {"production_decision": "INPUT_CHANGED", "production_fingerprint": "a" * 64},
        }
        self.assertEqual(
            select_production_worker_task([older, older_assessment, newer, production], "a" * 64),
            "task_production",
        )

    def test_verified_assessment_releases_one_queued_production_task(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        production = {
            "task_id": "task_production",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "input": {
                "production_decision": "SCHEDULE_DUE",
                "production_fingerprint": "a" * 64,
            },
        }
        self.assertEqual(
            select_production_worker_task([discovery, assessment, production], "a" * 64),
            "task_production",
        )


    def test_production_retry_respects_durable_not_before_backoff(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        production = {
            "task_id": "task_production_retry",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "not_before": "2026-11-10T00:00:30Z",
            "input": {
                "production_decision": "INPUT_CHANGED",
                "production_fingerprint": "a" * 64,
            },
        }
        before_backoff = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
        after_backoff = datetime(2026, 11, 10, 0, 0, 31, tzinfo=timezone.utc)
        self.assertEqual(
            select_production_worker_task([discovery, assessment, production], "a" * 64, now=before_backoff),
            "",
        )
        self.assertEqual(
            select_production_worker_task([discovery, assessment, production], "a" * 64, now=after_backoff),
            "task_production_retry",
        )

    def test_malformed_production_retry_timestamp_fails_closed(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        production = {
            "task_id": "task_bad_retry_time",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "not_before": "not-a-timestamp",
            "input": {"production_decision": "INPUT_CHANGED", "production_fingerprint": "a" * 64},
        }
        self.assertEqual(
            select_production_worker_task(
                [discovery, assessment, production],
                "a" * 64,
                now=datetime(2026, 11, 10, 0, 0, 31, tzinfo=timezone.utc),
            ),
            "",
        )


    def test_production_dispatch_stays_closed_without_verified_assessment(self):
        discovery = discovery_task(run_id="42417075148")
        production = {
            "task_id": "task_production",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "input": {"production_decision": "SCHEDULE_DUE", "production_fingerprint": "a" * 64},
        }
        self.assertEqual(select_production_worker_task([discovery, production], "a" * 64), "")

    def test_active_production_run_prevents_duplicate_dispatch(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148")
        active = {
            "task_id": "task_active_production",
            "target_program_id": "workflow_auto_sync",
            "status": "VERIFYING",
            "dispatch_intent": {"correlation_id": "already-dispatched"},
        }
        queued = {
            "task_id": "task_queued_production",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 100,
            "input": {"production_decision": "SCHEDULE_DUE", "production_fingerprint": "b" * 64},
        }
        self.assertEqual(select_production_worker_task([discovery, assessment, active, queued], "b" * 64), "")

    def test_invalid_assessment_does_not_release_production_task(self):
        discovery = discovery_task(run_id="42417075148")
        assessment = assessment_task("task_assessed", "42417075148", verified=False)
        production = {
            "task_id": "task_production",
            "target_program_id": "workflow_auto_sync",
            "status": "QUEUED",
            "lease": None,
            "dispatch_intent": None,
            "priority": 80,
            "input": {"production_decision": "SCHEDULE_DUE", "production_fingerprint": "a" * 64},
        }
        self.assertEqual(select_production_worker_task([discovery, assessment, production], "a" * 64), "")



class WatchdogAssessmentResumeContractTests(unittest.TestCase):
    def test_discovery_and_assessment_are_ordered_inside_one_production_run(self):
        workflow = (ROOT / ".github" / "workflows" / "auto_sync.yml").read_text(encoding="utf-8")
        self.assertIn("Discover candidate source repositories", workflow)
        self.assertIn("Assess discovered rule-list syntax", workflow)
        self.assertLess(workflow.index("Discover candidate source repositories"),
                        workflow.index("Assess discovered rule-list syntax"))
        self.assertFalse((ROOT / ".github" / "workflows" / "source-discovery.yml").exists())
        self.assertFalse((ROOT / ".github" / "workflows" / "assessment-completion-relay.yml").exists())

    def test_assessment_is_a_same_run_stage_not_an_independent_queue_target(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        programs = {item["id"]: item for item in registry["programs"]}
        self.assertNotIn("workflow_source_discovery", programs)
        self.assertIn("script_discover_sources", programs)
        self.assertIn("script_discover_sources", programs["script_assess_sources"]["depends_on"])
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"]
                       if item["target_program_id"] == "script_assess_sources")
        self.assertFalse(adapter["enabled"])
        self.assertEqual(adapter["allowed_callers"], [])
        workflow = (ROOT / ".github" / "workflows" / "auto_sync.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python3 scripts/assess_sources.py"), 1)

    def test_production_completion_dispatches_exact_run_to_watchdog(self):
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        production = (ROOT / ".github" / "workflows" / "auto_sync.yml").read_text(encoding="utf-8")
        self.assertIn("Wake Watchdog after production workflow completion", production)
        self.assertIn("PRODUCTION_RUN_ID: ${{ github.run_id }}", production)
        self.assertIn("automation-watchdog.yml/dispatches", production)
        self.assertIn("automation_task_id", watchdog)
        self.assertIn("workflow_dispatch", watchdog)

    def test_watchdog_reconciles_one_durable_task_per_supervision_cycle(self):
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("--max-tasks 1 run-once", watchdog)
        self.assertIn("verify_only", scheduler)
        self.assertIn("verify_pending", scheduler)


if __name__ == "__main__":
    unittest.main(verbosity=2)

if __name__ == "__main__":
    unittest.main(verbosity=2)
