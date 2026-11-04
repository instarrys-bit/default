from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def git_blob_sha(relative_path: str) -> str:
    return subprocess.run(
        ["git", "hash-object", relative_path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class CapabilityContractInventoryTests(unittest.TestCase):
    def test_inventory_is_pinned_to_the_current_program_registry(self):
        registry = load_json("automation/program_registry.json")
        inventory = load_json("automation/capability_contract_inventory.json")

        self.assertEqual(
            inventory["source_registry_blob_sha"],
            git_blob_sha("automation/program_registry.json"),
            "capability inventory must be regenerated when the program registry changes",
        )

        programs = registry["programs"]
        python_programs = [item for item in programs if item["kind"] == "python_component"]
        inventory_programs = inventory["programs"]
        self.assertEqual(inventory["summary"]["registered_programs"], len(programs))
        self.assertEqual(inventory["summary"]["python_components"], len(python_programs))
        self.assertEqual(len(inventory_programs), len(python_programs))

        registry_by_id = {item["id"]: item for item in python_programs}
        inventory_by_id = {item["id"]: item for item in inventory_programs}
        self.assertEqual(set(inventory_by_id), set(registry_by_id))

        for program_id, entry in inventory_by_id.items():
            registered = registry_by_id[program_id]
            self.assertEqual(entry["path"], registered["path"], program_id)
            self.assertEqual(entry["declared_capabilities"], registered["capabilities"], program_id)
            self.assertEqual(entry["registry_dependencies"], registered["depends_on"], program_id)
            self.assertEqual(entry["current_invocation"], registered["invocation"], program_id)

    def test_production_workflow_map_matches_current_workflow_and_registry_blobs(self):
        mapping = load_json("automation/production_workflow_map.json")
        workflow_path = ".github/workflows/auto_sync.yml"
        registry_path = "automation/program_registry.json"
        self.assertEqual(mapping["workflow_blob_sha"], git_blob_sha(workflow_path))
        self.assertEqual(mapping["registry_blob_sha"], git_blob_sha(registry_path))
        self.assertEqual(
            mapping["review_context"]["release_manifest_blob_sha"],
            git_blob_sha("automation/release_manifest.json"),
        )
        self.assertEqual(
            mapping["review_context"]["program_registry_blob_sha"],
            git_blob_sha(registry_path),
        )
        self.assertEqual(
            mapping["review_context"]["execution_adapters_blob_sha"],
            git_blob_sha("automation/execution_adapters.json"),
        )
        self.assertEqual(
            mapping["status"],
            "static_step_mapping_not_execution_authorization",
        )

        lines = (ROOT / workflow_path).read_text(encoding="utf-8").splitlines()
        actual_by_job = {}
        for job in mapping["job_graph"]:
            start = next(
                index for index, line in enumerate(lines)
                if line == f"  {job['id']}:"
            )
            end = next(
                (
                    index for index in range(start + 1, len(lines))
                    if lines[index].startswith("  ")
                    and not lines[index].startswith("    ")
                    and lines[index].rstrip().endswith(":")
                ),
                len(lines),
            )
            names = []
            for line in lines[start + 1:end]:
                match = re.match(r"^\s+- name:\s*(.+)$", line)
                if match:
                    names.append(match.group(1).strip().strip("\\\"'"))
            actual_by_job[job["id"]] = names
            mapped_names = [step["name"] for step in job["steps"]]
            self.assertEqual(mapped_names, names, job["id"])
            self.assertEqual(
                [step["order"] for step in job["steps"]],
                sorted(step["order"] for step in job["steps"]),
                job["id"],
            )

        actual_count = sum(len(names) for names in actual_by_job.values())
        self.assertEqual(mapping["summary"]["job_count"], len(mapping["job_graph"]))
        self.assertEqual(mapping["summary"]["step_count"], actual_count)

    def test_resource_write_inventory_is_pinned_to_current_release_and_components(self):
        writes = load_json("automation/resource_write_sets.json")
        release = load_json("automation/release_manifest.json")
        registry_path = "automation/program_registry.json"
        adapters_path = "automation/execution_adapters.json"
        self.assertEqual(writes["review_context"]["release_id"], release["release_id"])
        self.assertEqual(
            writes["review_context"]["release_manifest_blob_sha"],
            git_blob_sha("automation/release_manifest.json"),
        )
        self.assertEqual(
            writes["review_context"]["program_registry_blob_sha"],
            git_blob_sha(registry_path),
        )
        self.assertEqual(
            writes["review_context"]["execution_adapters_blob_sha"],
            git_blob_sha(adapters_path),
        )

    def test_assessment_remains_closed_until_all_dispatch_gates_pass(self):
        registry = load_json("automation/program_registry.json")
        adapters = load_json("automation/execution_adapters.json")
        inventory = load_json("automation/capability_contract_inventory.json")
        program = next(item for item in registry["programs"] if item["id"] == "script_assess_sources")
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        entry = next(item for item in inventory["programs"] if item["id"] == "script_assess_sources")
        self.assertFalse(program["orchestration"]["enabled"])
        self.assertEqual(program["orchestration"]["allowed_callers"], [])
        self.assertFalse(adapter["enabled"])
        self.assertEqual(adapter["allowed_callers"], [])
        self.assertEqual(entry["dispatch_status"], "disabled")
        self.assertEqual(inventory["summary"]["independently_dispatchable_python_components"], 0)

    def test_assessment_adapter_has_scheduler_enforced_typed_predecessor(self):
        adapters = load_json("automation/execution_adapters.json")
        contract = load_json("automation/capability_contracts/assess_sources.json")
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        self.assertEqual(adapter["dependency_contract"]["predecessor_program_id"], "script_discover_sources")
        self.assertEqual(adapter["dependency_contract"]["artifact_path"], "sources/discovered_sources.json")
        self.assertIn("predecessor", adapter["input_contract"]["required"])
        self.assertIn("scheduler.build_execution_plan", contract["dependency_edges"]["scheduler_enforcement"])
        self.assertFalse(adapter["enabled"])

    def test_assessment_restore_writer_is_registered_under_shared_mutex(self):
        audit = load_json("automation/resource_ownership_audit.json")
        writes = load_json("automation/resource_write_sets.json")
        registry = load_json("automation/program_registry.json")
        adapters = load_json("automation/execution_adapters.json")
        group = next(item for item in audit["resource_groups"] if item["id"] == "source_assessment_artifacts")
        entry = next(item for item in writes["confirmed_write_sets"] if item["program_id"] == "script_assess_sources")
        self.assertEqual(audit["evidence_scope"]["registry_blob_sha"], git_blob_sha("automation/program_registry.json"))
        self.assertEqual(audit["evidence_scope"]["adapters_blob_sha"], git_blob_sha("automation/execution_adapters.json"))
        self.assertIn("script_restore_automation_state", group["known_writers"])
        self.assertIn("workflow_auto_sync", group["known_writers"])
        self.assertIn("script_restore_automation_state", entry["additional_serialized_writers"])
        self.assertIn("logical/production-pipeline", entry["lease_keys"])
        restore = next(item for item in registry["programs"] if item["id"] == "script_restore_automation_state")
        self.assertFalse(restore["orchestration"]["enabled"])
        self.assertFalse(next(item for item in adapters["adapters"] if item["target_program_id"] == "script_restore_automation_state")["enabled"])

    def test_discovery_step_summary_is_not_a_shared_repository_resource(self):
        audit = load_json("automation/resource_ownership_audit.json")
        writes = load_json("automation/resource_write_sets.json")
        group = next(item for item in audit["resource_groups"] if item["id"] == "source_discovery_artifacts")
        entry = next(item for item in writes["confirmed_write_sets"] if item["program_id"] == "script_discover_sources")
        self.assertNotIn("GITHUB_STEP_SUMMARY", group["paths"])
        self.assertNotIn("GITHUB_STEP_SUMMARY", entry["writes"])
        self.assertTrue(any(item.startswith("GITHUB_STEP_SUMMARY") for item in entry["ephemeral_outputs"]))
        self.assertIn("reports/source-discovery.md", entry["writes"])
        self.assertIn("lease_required=True", entry["write_boundary_fencing"])
        self.assertIn("reports/source-discovery.md", entry["write_boundary_fencing"])

    def test_dashboard_report_writer_is_registered_in_shared_report_ownership(self):
        audit = load_json("automation/resource_ownership_audit.json")
        writes = load_json("automation/resource_write_sets.json")
        group = next(item for item in audit["resource_groups"] if item["id"] == "reports_and_audit_outputs")
        entry = next(item for item in writes["confirmed_write_sets"] if item["program_id"] == "script_build_project_status")
        self.assertIn("script_build_project_status", group["known_writers"])
        self.assertIn("reports/project-status.json", entry["writes"])
        self.assertIn("reports/project-status.md", entry["writes"])
        self.assertIn("scripts/build_project_status.py", audit["evidence_scope"]["inspected_sources"])

    def test_assessment_contract_dependency_matches_registry(self):
        registry = load_json("automation/program_registry.json")
        inventory = load_json("automation/capability_contract_inventory.json")
        contract = load_json("automation/capability_contracts/assess_sources.json")
        registered = next(item for item in registry["programs"] if item["id"] == "script_assess_sources")
        entry = next(item for item in inventory["programs"] if item["id"] == "script_assess_sources")
        self.assertIn("script_discover_sources", registered["depends_on"])
        self.assertEqual(entry["registry_dependencies"], registered["depends_on"])
        self.assertTrue(contract["dependency_edges"]["registry_dependency_declared"])
        self.assertEqual(
            contract["dependency_edges"]["registry_dependency_program_id"],
            "script_discover_sources",
        )
        self.assertEqual(
            contract["dependency_edges"]["required_predecessor_artifact"],
            "sources/discovered_sources.json",
        )

    def test_contract_sample_paths_and_implementation_pins_are_current(self):
        inventory = load_json("automation/capability_contract_inventory.json")
        for entry in inventory["programs"]:
            sample_path = entry.get("contract_sample_path")
            if not sample_path:
                continue
            sample_file = ROOT / sample_path
            self.assertTrue(sample_file.is_file(), f"{entry['id']} contract sample is missing")
            sample = json.loads(sample_file.read_text(encoding="utf-8"))
            self.assertEqual(sample["program_id"], entry["id"])
            self.assertEqual(sample["implementation_path"], entry["path"])
            self.assertEqual(
                sample["implementation_blob_sha"],
                git_blob_sha(entry["path"]),
                f"{entry['id']} contract sample points to stale implementation",
            )

    def test_inventory_dispatch_claims_match_python_adapter_enablement(self):
        inventory = load_json("automation/capability_contract_inventory.json")
        adapters = load_json("automation/execution_adapters.json")
        python_ids = {entry["id"] for entry in inventory["programs"]}
        adapter_by_id = {
            item["target_program_id"]: item
            for item in adapters["adapters"]
            if item["target_program_id"] in python_ids
        }
        self.assertEqual(set(adapter_by_id), python_ids)

        enabled_python = {
            program_id for program_id, adapter in adapter_by_id.items()
            if adapter.get("enabled") is True
        }
        declared_dispatchable = {
            entry["id"] for entry in inventory["programs"]
            if entry.get("dispatch_status") == "enabled"
        }
        self.assertEqual(declared_dispatchable, enabled_python)
        self.assertEqual(
            inventory["summary"]["independently_dispatchable_python_components"],
            len(enabled_python),
        )



    def test_owner_config_baseline_metadata_writer_is_inventoried_and_fenced(self):
        writes = load_json("automation/resource_write_sets.json")
        entry = next(
            item for item in writes["confirmed_write_sets"]
            if item["program_id"] == "script_register_config_baseline"
        )
        self.assertEqual(
            set(entry["writes"]),
            {
                "sources/policy.json",
                "automation/release_manifest.json",
                "automation/production_workflow_map.json",
                "automation/resource_write_sets.json",
            },
        )
        self.assertIn("logical/production-pipeline", entry["lease_keys"])
        self.assertIn("modules/uu.conf is read-only", entry["write_boundary_fencing"])

        ownership = load_json("automation/resource_ownership_audit.json")
        group = next(
            item for item in ownership["resource_groups"]
            if item["id"] == "owner_config_baseline_metadata"
        )
        self.assertEqual(group["lease_key"], "logical/production-pipeline")
        self.assertIn("script_register_config_baseline", group["writers"])
        self.assertEqual(ownership["status"], "partial_static_audit")


    def test_durable_task_queue_writers_are_classified_as_sha_cas_control_plane(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["confirmed_write_sets"]}
        remote = entries["script_remote_task_queue_runtime"]
        store = entries["script_github_queue_store"]
        self.assertEqual(remote["writes"], ["automation/task_queue.json"])
        self.assertEqual(store["writes"], ["automation/task_queue.json"])
        self.assertEqual(remote["control_plane_consistency"], "sha_cas")
        self.assertIn("blind writes are prohibited", remote["write_boundary_fencing"])
        group = next(
            item for item in writes["confirmed_shared_write_groups"]
            if item["resource"] == "durable task queue control-plane state"
        )
        self.assertEqual(group["mode"], "compare_and_swap")
        self.assertIn("workflow_automation_watchdog", group["writers"])

        ownership = load_json("automation/resource_ownership_audit.json")
        audit_group = next(
            item for item in ownership["resource_groups"]
            if item["id"] == "durable_task_queue_control_plane"
        )
        self.assertEqual(audit_group["status"], "sha_cas_control_plane_reviewed")
        self.assertEqual(ownership["status"], "partial_static_audit")


    def test_newly_identified_direct_writers_are_registered_with_scoped_outputs(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["confirmed_write_sets"]}
        required = {
            "script_lifecycle_gate",
            "script_import_request_observations",
            "script_build_rule_provenance",
            "script_restore_automation_state",
            "script_apply_safe_repair",
            "script_diagnose_workflow_failure",
            "script_incident_state",
            "script_persist_review_cursor",
            "script_production_intent",
            "script_task_scheduler",
            "script_build_dashboard_snapshot",
            "script_append_step_summary",
        }
        self.assertTrue(required.issubset(entries))
        self.assertEqual(entries["script_lifecycle_gate"]["writes"], ["rulesets/lifecycle_state.json"])
        self.assertIn("data/domain_candidates.json", entries["script_import_request_observations"]["writes"])
        self.assertIn("sources/rule_provenance.json", entries["script_build_rule_provenance"]["writes"])
        self.assertIn("logical/production-pipeline", entries["script_restore_automation_state"]["lease_keys"])
        self.assertEqual(entries["script_apply_safe_repair"]["publish_resources"], [])
        self.assertTrue(entries["script_diagnose_workflow_failure"]["ephemeral_unpublished_resources"])
        self.assertTrue(entries["script_incident_state"]["ephemeral_unpublished_resources"])
        self.assertIn("$RUNNER_TEMP/review_cursor.json", entries["script_persist_review_cursor"]["ephemeral_unpublished_resources"])
        self.assertEqual(entries["script_build_dashboard_snapshot"]["writes"], ["dashboard/data.json"])
        self.assertEqual(entries["script_append_step_summary"]["writes"], ["$GITHUB_STEP_SUMMARY"])
        self.assertTrue(all("modules/uu.conf" not in item["writes"] for item in entries.values()))
        self.assertEqual(writes["status"], "partial_static_entrypoint_review")

    def test_shared_document_and_workflow_cas_gaps_are_explicit(self):
        writes = load_json("automation/resource_write_sets.json")
        audit = load_json("automation/resource_ownership_audit.json")
        groups = {item["id"]: item for item in audit["resource_groups"]}
        self.assertIn("data/domain_candidates.json logical document", {item["resource"] for item in writes["confirmed_shared_write_groups"]})
        self.assertIn("sources/rule_provenance.json logical document", {item["resource"] for item in writes["confirmed_shared_write_groups"]})
        self.assertEqual(groups["domain_candidate_buffer"]["status"], "known_shared_writers_central_pipeline_fence_only")
        self.assertEqual(groups["rule_provenance_ledger"]["status"], "known_shared_writers_central_pipeline_fence_only")
        self.assertEqual(groups["watchdog_unregistered_path_registry"]["status"], "bounded_cas_retry_implemented_concurrent_integration_unproven")
        self.assertEqual(groups["request_intake_observations"]["status"], "rebase_retry_implemented_concurrent_integration_unproven")
        self.assertEqual(audit["status"], "partial_static_audit")

        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        self.assertIn("shadowrocket-request-intake-${{ github.run_id }}", intake)
        self.assertIn("git fetch origin main", intake)
        self.assertIn("git rebase origin/main", intake)
        self.assertIn("for attempt in 1 2 3; do", intake)
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("automation/unregistered_path_registry.json", watchdog)
        self.assertIn("-f sha=\"$registry_sha\"", watchdog)

    def test_dynamic_ephemeral_writers_are_not_misclassified_as_shared_repo_writers(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["confirmed_write_sets"]}
        self.assertIn("<caller-supplied --out path>", entries["script_incident_state"]["writes"])
        self.assertIn("/tmp/incident-state-body.md", entries["script_incident_state"]["ephemeral_unpublished_resources"])
        self.assertIn("<caller-supplied --destination path>", entries["script_persist_review_cursor"]["writes"])
        self.assertEqual(entries["script_persist_review_cursor"]["publish_resources"], [])
        self.assertIn("task-input.json", entries["script_task_scheduler"]["ephemeral_unpublished_resources"])
        self.assertEqual(entries["script_task_scheduler"]["publish_resources"], [])

if __name__ == "__main__":
    unittest.main()
