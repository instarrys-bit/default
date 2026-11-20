import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_release_manifest import _validate_config_baseline_pin, _validate_python_adapter_policy, validate_release_manifest


class ReleaseManifestSmokeTests(unittest.TestCase):
    def test_repository_manifest_passes_as_blocked_four_workflow_baseline(self):
        result = validate_release_manifest(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verified_git_blob_pins"], 6)
        self.assertEqual(result["independent_python_dispatch"], "blocked")
        self.assertEqual(result["python_adapters_enabled"], 0)

    def test_baseline_snapshot_does_not_claim_live_independent_handoff(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["release_status"], "baseline_snapshot")
        self.assertEqual(manifest["python_adapter_policy"]["allowed_adapters"], [])
        self.assertEqual(manifest["next_migration_gate"]["completion_status"], "blocked_pending_contract_and_runtime_enforcement")

    def test_release_pins_are_immutable_baseline_references(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
        for item in manifest["component_schemas"].values():
            self.assertTrue(item["path"])
            self.assertEqual(len(item["git_blob_sha"]), 40)
            self.assertTrue(all(char in "0123456789abcdef" for char in item["git_blob_sha"]))
        for item in manifest["implementation_pins"].values():
            if not isinstance(item, dict) or "path" not in item:
                continue
            self.assertTrue(item["path"])
            digest = item.get("git_blob_sha")
            if digest is not None:
                self.assertEqual(len(digest), 40)
                self.assertTrue(all(char in "0123456789abcdef" for char in digest))

    def test_config_release_pin_matches_owner_approved_baseline(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
        config_pin = manifest["implementation_pins"]["config_baseline"]
        _validate_config_baseline_pin(ROOT, config_pin)
        with self.assertRaisesRegex(ValueError, "owner-approved"):
            _validate_config_baseline_pin(ROOT, {**config_pin, "git_blob_sha": "0" * 40})

    def test_empty_default_deny_allowlist_rejects_enabled_python_adapter(self):
        adapters = json.loads((ROOT / "automation/execution_adapters.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "automation/program_registry.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        adapter["enabled"] = True
        with self.assertRaisesRegex(ValueError, "enabled Python adapters and exact release allowlist differ"):
            _validate_python_adapter_policy(
                ROOT, {"schema_version": 1, "default_decision": "deny", "allowed_adapters": []},
                adapters, registry, "shadowrocket-automation-baseline-2026.11.20.1",
            )


if __name__ == "__main__":
    unittest.main()
