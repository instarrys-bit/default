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
