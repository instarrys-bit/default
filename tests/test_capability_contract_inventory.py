from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def blob_sha(path: str) -> str:
    return subprocess.run(
        ["git", "hash-object", path], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


class CapabilityContractInventoryTests(unittest.TestCase):
    def test_inventory_is_retained_as_archival_not_dispatch_authority(self):
        inventory = read_json("automation/capability_contract_inventory.json")
        self.assertEqual(inventory["status"], "retired_archival_snapshot")
        note = inventory["review_context"]["note"]
        self.assertIn("not an activation authority", note)
        self.assertIn("four workflows", note)
        self.assertGreater(len(inventory["programs"]), 0)

    def test_production_workflow_map_matches_current_workflow_and_registry_blobs(self):
        mapping = read_json("automation/production_workflow_map.json")
        self.assertEqual(mapping["workflow_blob_sha"], blob_sha(".github/workflows/auto_sync.yml"))
        self.assertEqual(mapping["registry_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(mapping["review_context"]["program_registry_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(mapping["review_context"]["execution_adapters_blob_sha"], blob_sha("automation/execution_adapters.json"))
        self.assertEqual(mapping["status"], "static_step_mapping_not_execution_authorization")

    def test_resource_write_inventory_is_current_and_pinned(self):
        writes = read_json("automation/resource_write_sets.json")
        release = read_json("automation/release_manifest.json")
        self.assertEqual(writes["status"], "partial_static_entrypoint_review")
        self.assertEqual(writes["review_context"]["release_id"], release["release_id"])
        self.assertEqual(writes["review_context"]["release_manifest_blob_sha"], blob_sha("automation/release_manifest.json"))
        self.assertEqual(writes["review_context"]["program_registry_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(writes["review_context"]["execution_adapters_blob_sha"], blob_sha("automation/execution_adapters.json"))

    def test_assessment_adapter_is_disabled_under_monolithic_four_workflow_design(self):
        registry = read_json("automation/program_registry.json")
        adapters = read_json("automation/execution_adapters.json")
        program = next(x for x in registry["programs"] if x["id"] == "script_assess_sources")
        adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "script_assess_sources")
        self.assertFalse(program["orchestration"]["enabled"])
        self.assertEqual(program["orchestration"]["allowed_callers"], [])
        self.assertFalse(adapter["enabled"])
        self.assertEqual(adapter["allowed_callers"], [])
        self.assertEqual(adapter["write_resources"], [])
        self.assertEqual(adapter["publish_resources"], [])
        workflow = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("python3 scripts/assess_sources.py"), 1)
        self.assertFalse((ROOT / ".github/workflows/source-discovery.yml").exists())

    def test_assessment_dependency_is_registered_but_not_independently_dispatchable(self):
        registry = read_json("automation/program_registry.json")
        adapters = read_json("automation/execution_adapters.json")
        program = next(x for x in registry["programs"] if x["id"] == "script_assess_sources")
        adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "script_assess_sources")
        self.assertIn("script_discover_sources", program["depends_on"])
        self.assertFalse(adapter["enabled"])
        self.assertIsNone(adapter.get("dependency_contract"))
        workflow = (ROOT / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertLess(workflow.index("Discover candidate source repositories"), workflow.index("Assess discovered rule-list syntax"))

    def test_restore_writer_is_registered_and_publication_is_rulesets_only(self):
        writes = read_json("automation/resource_write_sets.json")
        entry = next(x for x in writes["confirmed_write_sets"] if x["program_id"] == "script_restore_automation_state")
        self.assertTrue(entry["lease_keys"])
        self.assertEqual(entry["publish_resources"], ["rulesets/**"])
        self.assertNotIn("modules/uu.conf", entry["writes"])

    def test_discovery_step_summary_is_run_local_not_shared_repository_state(self):
        writes = read_json("automation/resource_write_sets.json")
        entry = next(x for x in writes["confirmed_write_sets"] if x["program_id"] == "script_discover_sources")
        self.assertTrue(any("GITHUB_STEP_SUMMARY" in x for x in entry.get("ephemeral_outputs", [])))
        self.assertNotIn("GITHUB_STEP_SUMMARY", entry["writes"])
        self.assertTrue(any("$AUTOMATION_ARTIFACT_ROOT" in x for x in entry["writes"]))

    def test_dashboard_report_writer_is_classified_as_runner_local(self):
        audit = read_json("automation/resource_ownership_audit.json")
        writes = read_json("automation/resource_write_sets.json")
        group = next(x for x in audit["resource_groups"] if x["id"] == "reports_and_audit_outputs")
        entry = next(x for x in writes["confirmed_write_sets"] if x["program_id"] == "script_build_project_status")
        self.assertIn("script_build_project_status", group["known_writers"])
        self.assertIn("reports/project-status.json", entry["writes"])
        self.assertIn("reports/project-status.md", entry["writes"])
        self.assertEqual(group["status"], "runner_local_artifacts_no_repository_publication")

    def test_assessment_contract_declares_the_discovery_predecessor(self):
        registry = read_json("automation/program_registry.json")
        contract = read_json("automation/capability_contracts/assess_sources.json")
        program = next(x for x in registry["programs"] if x["id"] == "script_assess_sources")
        self.assertIn("script_discover_sources", program["depends_on"])
        self.assertEqual(contract["dependency_edges"]["registry_dependency_program_id"], "script_discover_sources")
        self.assertEqual(contract["dependency_edges"]["required_predecessor_artifact"], "sources/discovered_sources.json")

    def test_release_manifest_pins_current_registry_and_adapter_blobs(self):
        release = read_json("automation/release_manifest.json")
        self.assertEqual(release["component_schemas"]["program_registry"]["git_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(release["component_schemas"]["execution_adapters"]["git_blob_sha"], blob_sha("automation/execution_adapters.json"))
        self.assertEqual(release["implementation_pins"]["program_registry"]["git_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(release["implementation_pins"]["execution_adapters"]["git_blob_sha"], blob_sha("automation/execution_adapters.json"))
        self.assertEqual(release["implementation_pins"]["storage_management_workflow"]["git_blob_sha"], blob_sha(".github/workflows/storage-management.yml"))
        self.assertEqual(release["implementation_pins"]["storage_auto_sync_recovery_verifier"]["git_blob_sha"], blob_sha("storage/v2/verify_auto_sync_recovery.py"))
        self.assertTrue(release["execution_policy"]["existing_adapter_enablement_unchanged"])

    def test_adapter_enablement_matches_registry_and_default_deny(self):
        registry = read_json("automation/program_registry.json")
        adapters = read_json("automation/execution_adapters.json")
        python_programs = {x["id"]: x for x in registry["programs"] if x["kind"] == "python_component"}
        adapter_by_id = {x["target_program_id"]: x for x in adapters["adapters"]}
        self.assertTrue(set(python_programs).issubset(adapter_by_id))
        for program_id, program in python_programs.items():
            self.assertEqual(adapter_by_id[program_id].get("enabled") is True,
                             program.get("orchestration", {}).get("enabled") is True)
        self.assertTrue(all(not adapter_by_id[x].get("enabled") for x in python_programs))

    def test_owner_config_baseline_is_read_only_and_file_management_tracks_sha(self):
        policy = read_json("sources/policy.json")
        guard = policy["managed_config_guard"]
        self.assertFalse(guard["content_protection"]["automation_may_modify_content"])
        self.assertTrue(guard["baseline_metadata_policy"]["automation_may_hash_file"])
        self.assertTrue(guard["baseline_metadata_policy"]["automation_may_update_registered_blob_sha"])
        self.assertIn("File Management", guard["baseline_metadata_policy"]["update_authorization"])
        script = (ROOT / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
        self.assertNotIn("--apply", script)
        workflow = (ROOT / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
        self.assertNotIn("reconcile-config-baseline:", workflow)

    def test_durable_queue_writers_are_classified_as_control_plane_not_production_publishers(self):
        writes = read_json("automation/resource_write_sets.json")
        entries = {x["program_id"]: x for x in writes["control_plane_side_effects"]}
        remote = entries["script_remote_task_queue_runtime"]
        store = entries["storage_queue_store"]
        self.assertIn("automation/task_queue.json", " ".join(remote["side_effects"]))
        self.assertIn("automation/task_queue.json Contents API SHA-CAS updates", " ".join(store["side_effects"]))
        self.assertIn("Contents API SHA-CAS", remote["control_plane_boundary"])
        self.assertIn("No Issues API", store["control_plane_boundary"])
        self.assertIn("modules/**", store["control_plane_boundary"])
        self.assertIn("rulesets/**", store["control_plane_boundary"])

    def test_ruleset_writers_publish_only_to_rulesets(self):
        writes = read_json("automation/resource_write_sets.json")
        for entry in writes["confirmed_write_sets"]:
            for resource in entry.get("publish_resources", []):
                self.assertTrue(resource == "rulesets/**" or resource.startswith("rulesets/"), entry["program_id"])
            self.assertNotIn("modules/uu.conf", entry.get("writes", []))
        self.assertEqual(writes["policy"]["protected_config"]["access"], "read_only")
        self.assertEqual(writes["policy"]["protected_config"]["writers_allowed"], [])

    def test_shared_document_store_and_workflow_state_cas_are_explicit(self):
        writes = read_json("automation/resource_write_sets.json")
        groups = {x["resource"]: x for x in writes["confirmed_shared_write_groups"]}
        self.assertIn("data/domain_candidates.json logical document", groups)
        self.assertIn("sources/rule_provenance.json logical document", groups)
        store = next(x for x in writes["confirmed_write_sets"] if x["program_id"] == "script_json_document_store")
        self.assertTrue(store["lease_keys"])
        control_ids = {x["program_id"] for x in writes["control_plane_side_effects"]}
        self.assertIn("storage_runtime", control_ids)
        self.assertEqual(writes["status"], "partial_static_entrypoint_review")

    def test_dynamic_ephemeral_writers_are_not_misclassified_as_shared_repository_writers(self):
        writes = read_json("automation/resource_write_sets.json")
        nonwriters = {x["program_id"]: x for x in writes["reviewed_non_writers"]}
        self.assertEqual(nonwriters["script_incident_state"]["classification"], "storage_state_transition_library_non_writer")
        self.assertIn("no filesystem or network writes", nonwriters["script_incident_state"]["evidence"])
        self.assertEqual(nonwriters["script_persist_review_cursor"]["classification"], "runner_local_failed_cursor_recovery_artifact_non_dispatchable")
        self.assertEqual(nonwriters["storage_dashboard_snapshot"]["classification"], "runner_local_ephemeral_output_non_dispatchable")
        self.assertEqual(nonwriters["storage_watchdog_supervisor"]["classification"], "runner_local_step_summary_output_non_dispatchable")
        self.assertEqual(nonwriters["script_run_preflight_tests"]["classification"], "runner_local_test_execution_non_dispatchable")
        self.assertEqual(nonwriters["script_validate_automation_write_boundary"]["classification"], "read_only_automation_write_boundary_validator")


    def test_storage_recovery_verifier_is_read_only_and_not_independently_dispatchable(self):
        registry = read_json("automation/program_registry.json")
        adapters = read_json("automation/execution_adapters.json")
        writes = read_json("automation/resource_write_sets.json")
        program = next(x for x in registry["programs"] if x["id"] == "storage_verify_auto_sync_recovery")
        adapter = next(x for x in adapters["adapters"] if x["target_program_id"] == "storage_verify_auto_sync_recovery")
        nonwriter = next(x for x in writes["reviewed_non_writers"] if x["program_id"] == "storage_verify_auto_sync_recovery")
        self.assertFalse(program["orchestration"]["enabled"])
        self.assertEqual(program["orchestration"]["allowed_callers"], [])
        self.assertFalse(adapter["enabled"])
        self.assertEqual(adapter["allowed_callers"], [])
        self.assertEqual(adapter["write_resources"], [])
        self.assertEqual(adapter["publish_resources"], [])
        self.assertEqual(nonwriter["classification"], "read_only_recovery_verifier")
        self.assertIn("modules/uu.conf solely for integrity fingerprinting", nonwriter["evidence"])

    def test_every_registered_python_component_has_one_explicit_side_effect_classification(self):
        registry = read_json("automation/program_registry.json")
        writes = read_json("automation/resource_write_sets.json")
        python_ids = {x["id"] for x in registry["programs"] if x["kind"] == "python_component"}
        writer_ids = {x["program_id"] for x in writes["confirmed_write_sets"]}
        nonwriter_ids = {x["program_id"] for x in writes["reviewed_non_writers"]}
        control_ids = {x["program_id"] for x in writes["control_plane_side_effects"]}
        self.assertFalse(writer_ids & nonwriter_ids)
        self.assertFalse(writer_ids & control_ids)
        self.assertFalse(nonwriter_ids & control_ids)
        self.assertEqual(writer_ids | nonwriter_ids | control_ids, python_ids)
        self.assertEqual(len(python_ids), 69)
        self.assertEqual(writes["direct_mutation_scan"]["registered_component_count"], len(python_ids))


if __name__ == "__main__":
    unittest.main()
