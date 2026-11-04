from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
