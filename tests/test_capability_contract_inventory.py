from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def blob_sha(relative: str) -> str:
    return subprocess.run(
        ["git", "hash-object", relative], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


class CapabilityContractInventoryTests(unittest.TestCase):
    def test_registry_and_adapter_inventory_cover_exact_current_programs(self):
        registry = load("automation/program_registry.json")
        adapters = load("automation/execution_adapters.json")
        program_ids = {item["id"] for item in registry["programs"]}
        adapter_ids = {item["target_program_id"] for item in adapters["adapters"]}
        self.assertEqual(program_ids, adapter_ids)
        paths = {item["path"] for item in registry["programs"] if item["kind"] == "github_actions_workflow"}
        self.assertEqual(paths, {
            ".github/workflows/auto_sync.yml",
            ".github/workflows/automation-watchdog.yml",
            ".github/workflows/dashboard-pages.yml",
            ".github/workflows/storage-management.yml",
        })

    def test_registry_dispatch_graph_matches_consolidated_four_workflow_design(self):
        registry = load("automation/program_registry.json")
        by_id = {item["id"]: item for item in registry["programs"]}
        self.assertEqual(
            set(by_id["workflow_auto_sync"]["dispatches"]),
            {"workflow_storage_management", "workflow_automation_watchdog"},
        )
        self.assertEqual(by_id["workflow_automation_watchdog"]["dispatches"], ["workflow_auto_sync"])
        self.assertEqual(by_id["workflow_storage_management"]["dispatches"], [])
        self.assertEqual(by_id["workflow_dashboard_pages"]["dispatches"], [])

    def test_release_gate_does_not_enable_retired_independent_assessment_dispatch(self):
        control = load("automation/production_control.json")
        release = load("automation/release_manifest.json")
        adapters = load("automation/execution_adapters.json")
        assessment = next(x for x in adapters["adapters"] if x["target_program_id"] == "script_assess_sources")
        self.assertEqual(control["source_discovery_mode"], "monolithic_fallback")
        self.assertEqual(release["next_migration_gate"]["completion_status"], "blocked_pending_contract_and_runtime_enforcement")
        self.assertEqual(release["python_adapter_policy"]["allowed_adapters"], [])
        self.assertFalse(assessment["enabled"])
        self.assertFalse((ROOT / ".github/workflows/source-discovery.yml").exists())

    def test_production_publication_is_rulesets_only_and_config_is_protected(self):
        adapters = load("automation/execution_adapters.json")
        control = load("automation/production_control.json")
        production = next(x for x in adapters["adapters"] if x["target_program_id"] == "workflow_auto_sync")
        self.assertEqual(control["policy"]["protected_config"], "modules/uu.conf remains read-only")
        self.assertTrue(production["resource_contract"]["fencing_required"])
        self.assertTrue(all(path.startswith(("rulesets/", "logical/")) or path.startswith(("data/", "sources/", "reports/")) for path in production["resource_contract"]["resource_keys"]))
        self.assertFalse(any("modules/uu.conf" in x for x in production.get("write_resources", [])))
        self.assertFalse(any("modules/uu.conf" in x for x in production.get("publish_resources", [])))

    def test_inventory_snapshots_are_explicitly_pinned_to_current_components(self):
        mapping = load("automation/production_workflow_map.json")
        writes = load("automation/resource_write_sets.json")
        release = load("automation/release_manifest.json")
        self.assertEqual(mapping["workflow_blob_sha"], blob_sha(".github/workflows/auto_sync.yml"))
        self.assertEqual(mapping["registry_blob_sha"], blob_sha("automation/program_registry.json"))
        self.assertEqual(mapping["review_context"]["release_manifest_blob_sha"], blob_sha("automation/release_manifest.json"))
        self.assertEqual(mapping["review_context"]["execution_adapters_blob_sha"], blob_sha("automation/execution_adapters.json"))
        self.assertEqual(writes["review_context"]["release_id"], release["release_id"])
        self.assertEqual(writes["workflow_native_scan"]["workflow_count"], 4)
        for item in writes["confirmed_write_sets"]:
            self.assertNotIn("modules/uu.conf", item.get("writes", []))
            self.assertNotIn("modules/uu.conf", item.get("publish_resources", []))


if __name__ == "__main__":
    unittest.main()
