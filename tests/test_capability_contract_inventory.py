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

    def test_assessment_adapter_remains_disabled_until_issue_193_and_live_canary(self):
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
        workflow = Path(".github/workflows/automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("Enqueue source assessment after successful discovery workflow", workflow)
        assessment_step = workflow.split("Enqueue source assessment after successful discovery workflow", 1)[1].split("Resolve superseded historical DEAD_LETTER", 1)[0]
        self.assertIn("Shadowrocket Source Discovery (Watchdog)", assessment_step)
        self.assertNotIn("Shadowrocket Deterministic Domain Audit (User Config Baseline)", assessment_step)
        audit = Path(".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertEqual(audit.count("python3 scripts/discover_sources.py"), 1)
        self.assertEqual(audit.count("python3 scripts/assess_sources.py"), 1)

    def test_assessment_adapter_has_scheduler_enforced_typed_predecessor(self):
        adapters = load_json("automation/execution_adapters.json")
        contract = load_json("automation/capability_contracts/assess_sources.json")
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        self.assertEqual(adapter["dependency_contract"]["predecessor_program_id"], "script_discover_sources")
        self.assertEqual(adapter["dependency_contract"]["artifact_path"], "sources/discovered_sources.json")
        self.assertIn("predecessor", adapter["input_contract"]["required"])
        self.assertIn("scheduler.build_execution_plan", contract["dependency_edges"]["scheduler_enforcement"])
        self.assertFalse(adapter["enabled"])
        self.assertEqual(adapter["allowed_callers"], [])
        self.assertEqual(adapter["write_resources"], [])
        self.assertEqual(adapter["publish_resources"], [])
        self.assertEqual(adapter["dependency_contract"]["producer_workflow_name"], "Shadowrocket Source Discovery (Watchdog)")

    def test_assessment_restore_writer_is_registered_under_shared_mutex(self):
        audit = load_json("automation/resource_ownership_audit.json")
        writes = load_json("automation/resource_write_sets.json")
        registry = load_json("automation/program_registry.json")
        adapters = load_json("automation/execution_adapters.json")
        group = next(item for item in audit["resource_groups"] if item["id"] == "source_assessment_artifacts")
        entry = next(item for item in writes["confirmed_write_sets"] if item["program_id"] == "script_assess_sources")
        self.assertEqual(audit["evidence_scope"]["registry_blob_sha"], git_blob_sha("automation/program_registry.json"))
        self.assertEqual(audit["evidence_scope"]["adapters_blob_sha"], git_blob_sha("automation/execution_adapters.json"))
        self.assertEqual(group["status"], "runner_local_artifacts_no_repository_publication")
        self.assertEqual(group["known_writers"], ["script_assess_sources"])
        self.assertEqual(entry["additional_serialized_writers"], [])
        self.assertEqual(entry["publish_resources"], [])
        self.assertIn("logical/source-assessment-checkpoints", entry["lease_keys"])
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
        self.assertIn("$AUTOMATION_ARTIFACT_ROOT/reports/source-discovery.md", entry["writes"])
        self.assertIn("RUNNER_TEMP", entry["write_boundary_fencing"])
        self.assertNotIn("lease_required=True", entry["write_boundary_fencing"])

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
            item for item in writes["reviewed_non_writers"]
            if item["program_id"] == "script_register_config_baseline"
        )
        self.assertEqual(entry["classification"], "runner_local_config_baseline_review_proposal_non_dispatchable")
        self.assertIn("RUNNER_TEMP/config-baseline-proposal.json", entry["evidence"])
        self.assertIn("never writes", entry["evidence"])

        ownership = load_json("automation/resource_ownership_audit.json")
        group = next(
            item for item in ownership["resource_groups"]
            if item["id"] == "owner_config_baseline_metadata"
        )
        self.assertEqual(group["status"], "no_repository_metadata_writer")
        self.assertEqual(group["known_writers"], [])
        self.assertEqual(ownership["status"], "partial_static_audit")


    def test_durable_task_queue_writers_are_classified_as_issue_snapshot_control_plane(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["control_plane_side_effects"]}
        remote = entries["script_remote_task_queue_runtime"]
        store = entries["script_github_queue_store"]
        self.assertEqual(remote["writes"], ["GitHub Issue #315 comment snapshots (external durable queue state)"])
        self.assertEqual(store["writes"], ["GitHub Issue #315 comment snapshots (external durable queue state)"])
        self.assertEqual(remote["control_plane_consistency"], "append_only_issue_snapshot_chain")
        self.assertIn("No GitHub Contents API", remote["write_boundary_fencing"])
        group = next(
            item for item in writes["confirmed_shared_write_groups"]
            if item["resource"] == "durable task queue control-plane state"
        )
        self.assertEqual(group["mode"], "append_only_revision_chain")
        self.assertIn("workflow_automation_watchdog", group["writers"])
        self.assertIn("script_resource_lease_runtime", group["writers"])

        ownership = load_json("automation/resource_ownership_audit.json")
        audit_group = next(
            item for item in ownership["resource_groups"]
            if item["id"] == "durable_task_queue_control_plane"
        )
        self.assertEqual(audit_group["status"], "append_only_issue_snapshot_chain_reviewed")
        self.assertIn("script_resource_lease_runtime", audit_group["writers"])
        self.assertEqual(ownership["status"], "partial_static_audit")


    def test_newly_identified_direct_writers_are_registered_with_scoped_outputs(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["confirmed_write_sets"]}
        nonwriters = {item["program_id"]: item for item in writes["reviewed_non_writers"]}
        required_writers = {
            "script_lifecycle_gate", "script_import_request_observations",
            "script_build_rule_provenance", "script_restore_automation_state",
            "script_apply_safe_repair", "script_task_scheduler",
            "script_audit_source_lineage", "script_audit_policy_source_overlap",
            "script_audit_external_domains", "script_audit_config_drift",
            "script_audit_ruleset_references", "script_audit_ruleset_config_overlap",
            "script_json_document_store", "script_resource_lease_runtime",
        }
        self.assertTrue(required_writers.issubset(entries))
        self.assertEqual(entries["script_lifecycle_gate"]["writes"], ["rulesets/lifecycle_state.json"])
        self.assertIn("data/domain_candidates.json", entries["script_import_request_observations"]["writes"])
        self.assertIn("sources/rule_provenance.json", entries["script_build_rule_provenance"]["writes"])
        self.assertEqual(entries["script_restore_automation_state"]["publish_resources"], ["rulesets/**"])
        self.assertEqual(entries["script_apply_safe_repair"]["publish_resources"], [])
        self.assertEqual(entries["script_json_document_store"]["publish_resources"], [])
        self.assertEqual(entries["script_audit_policy_source_overlap"]["publish_resources"], [])
        self.assertEqual(n in nonwriters for n in ("script_auto_activate_sources", "script_persist_review_cursor", "script_incident_state")), True
        self.assertTrue(all("modules/uu.conf" not in item["writes"] for item in entries.values()))
        self.assertEqual(writes["status"], "partial_static_entrypoint_review")

    def test_shared_document_and_workflow_cas_gaps_are_explicit(self):
        writes = load_json("automation/resource_write_sets.json")
        audit = load_json("automation/resource_ownership_audit.json")
        groups = {item["id"]: item for item in audit["resource_groups"]}
        self.assertIn("data/domain_candidates.json logical document", {item["resource"] for item in writes["confirmed_shared_write_groups"]})
        self.assertIn("sources/rule_provenance.json logical document", {item["resource"] for item in writes["confirmed_shared_write_groups"]})
        self.assertEqual(groups["domain_candidate_buffer"]["status"], "fenced_at_each_document_store_mutation")
        self.assertEqual(groups["rule_provenance_ledger"]["status"], "fenced_at_each_document_store_mutation")
        self.assertEqual(groups["watchdog_unregistered_path_registry"]["status"], "bounded_cas_retry_implemented_concurrent_integration_unproven")
        self.assertEqual(groups["request_intake_observations"]["status"], "external_issue_ledger_read_by_production_fingerprint_and_candidate_importer")
        self.assertIn("workflow_request_intake", groups["request_intake_observations"]["known_writers"])
        self.assertEqual(groups["active_source_registry_and_activation"]["status"], "no_repository_writer_source_activation_artifact_only")
        self.assertEqual(groups["policy_source_overlap_audit"]["status"], "artifact_only_no_repository_publication")
        doc_store = groups["shared_json_document_store"]
        self.assertIn("script_json_document_store", doc_store["known_writers"])
        self.assertIn("script_resource_lease_runtime", groups["durable_task_queue_control_plane"]["writers"])
        self.assertEqual(groups["active_source_registry_and_activation"]["known_writers"], [])
        self.assertNotIn("script_restore_automation_state", groups["source_candidate_artifacts"]["known_writers"])
        self.assertEqual(groups["source_discovery_artifacts"]["known_writers"], ["script_discover_sources", "workflow_source_discovery"])
        self.assertIn("script_restore_automation_state", groups["published_ruleset_artifacts"]["known_writers"])
        self.assertIn("script_restore_automation_state", groups["ruleset_manifest"]["known_writers"])
        self.assertEqual(audit["status"], "partial_static_audit")

        intake = (ROOT / ".github" / "workflows" / "request-intake.yml").read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-domain-intake", intake)
        self.assertIn("contents: read", intake)
        self.assertIn("issues: write", intake)
        self.assertIn("issues/317/comments", intake)
        self.assertNotIn("git push", intake)
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn("Production input classification requires review", watchdog)
        self.assertNotIn('gh api --method PUT "repos/$REPO/contents/automation/unregistered_path_registry.json"', watchdog)

    def test_dynamic_ephemeral_writers_are_not_misclassified_as_shared_repo_writers(self):
        writes = load_json("automation/resource_write_sets.json")
        entries = {item["program_id"]: item for item in writes["confirmed_write_sets"]}
        self.assertIn("<caller-supplied --out path>", entries["script_incident_state"]["writes"])
        self.assertIn("/tmp/incident-state-body.md", entries["script_incident_state"]["ephemeral_unpublished_resources"])
        self.assertEqual(entries["script_persist_review_cursor"]["writes"], ["sources/review_cursor.json"])
        self.assertEqual(entries["script_persist_review_cursor"]["publish_resources"], ["sources/review_cursor.json"])
        self.assertIn("task-input.json", entries["script_task_scheduler"]["ephemeral_unpublished_resources"])
        self.assertEqual(entries["script_task_scheduler"]["publish_resources"], [])


    def test_every_registered_python_component_has_an_explicit_write_side_effect_classification(self):
        registry = load_json("automation/program_registry.json")
        writes = load_json("automation/resource_write_sets.json")
        python_ids = {item["id"] for item in registry["programs"] if item["kind"] == "python_component"}
        writer_ids = {item["program_id"] for item in writes["confirmed_write_sets"]}
        nonwriter_ids = {item["program_id"] for item in writes["reviewed_non_writers"]}
        external_ids = {item["program_id"] for item in writes["control_plane_side_effects"]}
        self.assertFalse(writer_ids & nonwriter_ids)
        self.assertFalse(writer_ids & external_ids)
        self.assertFalse(nonwriter_ids & external_ids)
        self.assertEqual(writer_ids | nonwriter_ids | external_ids, python_ids)
        self.assertEqual(len(writer_ids), 25)
        self.assertEqual(len(nonwriter_ids), 24)
        self.assertEqual(external_ids, {"script_github_workflow_adapter", "script_github_queue_store", "script_remote_task_queue_runtime"})
        self.assertIn("script_resource_lease_runtime", writer_ids)
        self.assertIn("script_json_document_store", writer_ids)

if __name__ == "__main__":
    unittest.main()
