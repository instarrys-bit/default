#!/usr/bin/env python3
"""Run the maintained deterministic production preflight suite.

Legacy V1 split-DAG, retired workflow-topology, and superseded repository-writer
contract tests remain available in the repository for historical reference, but
are not production gates for the consolidated four-workflow pipeline. Storage
Management's V2 suite is run independently by the existing Storage Management
workflow.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

ACTIVE_TEST_MODULES = (
    "test_append_step_summary",
    "test_audit_source_lineage",
    "test_auto_activate_sources",
    "test_baseline_registration_verifier",
    "test_build_project_status",
    "test_build_rulesets_capacity",
    "test_config_baseline_registration",
    "test_config_conflict_run_report",
    "test_config_drift",
    "test_config_scope_precedence",
    "test_correlated_evidence_gate",
    "test_domain_wildcard_config_validation",
    "test_execution_adapters",
    "test_external_intelligence_catalog",
    "test_json_document_store",
    "test_lifecycle_audit",
    "test_lifecycle_gate",
    "test_managed_config_guard_policy",
    "test_network_retry",
    "test_policy_source_overlap",
    "test_production_intent",
    "test_program_registry",
    "test_publication_accounting",
    "test_publish_base_integration",
    "test_refresh_ruleset_manifest",
    "test_release_manifest",
    "test_reject_automatic_publication",
    "test_restore_automation_state",
    "test_review_cursor",
    "test_rule_provenance",
    "test_ruleset_config_conflict_sync",
    "test_ruleset_config_overlap",
    "test_ruleset_references",
    "test_source_candidate_lineage",
    "test_source_line_provenance",
    "test_source_quarantine_quality_gate",
    "test_suffix_scope_safety",
    "test_verify_baseline",
    "test_verify_published_rulesets",
    "test_verify_recovery_run",
    "test_watchdog_recovery_policy",
    "test_workflow_scheduler_integration",
    "test_remote_task_queue_runtime",
    "test_resource_lease_runtime",
    "test_task_result_verifier",
    "test_task_queue_runtime",
    "test_task_queue",
    "test_workflow_native_write_inventory",
    "test_current_workflow_contracts",
)


def count_tests(suite: unittest.TestSuite) -> int:
    return sum(count_tests(item) if isinstance(item, unittest.TestSuite) else 1 for item in suite)


def main() -> int:
    loader = unittest.TestLoader()
    combined = unittest.TestSuite()
    missing = []
    for module in ACTIVE_TEST_MODULES:
        try:
            suite = loader.loadTestsFromName(module)
        except Exception as exc:
            missing.append(f"{module}: {exc}")
            continue
        if isinstance(suite, unittest.TestSuite) and count_tests(suite) == 0:
            missing.append(f"{module}: no tests discovered")
        combined.addTests(suite)

    if missing:
        print("Preflight suite definition is invalid:", *missing, sep="\n- ", file=sys.stderr)
        return 2

    print(f"Running {count_tests(combined)} tests from {len(ACTIVE_TEST_MODULES)} maintained modules.")
    result = unittest.TextTestRunner(verbosity=2).run(combined)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
