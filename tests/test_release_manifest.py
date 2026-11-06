import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_release_manifest import (
    _canonical_digest,
    _validate_config_baseline_pin,
    _validate_python_adapter_policy,
    validate_release_manifest,
)


class ReleaseManifestSmokeTests(unittest.TestCase):
    def test_repository_manifest_passes(self):
        result = validate_release_manifest(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verified_git_blob_pins"], 6)
        self.assertEqual(result["independent_python_dispatch"], "blocked")


    def test_release_pins_are_immutable_baseline_references(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))

        # Release pins identify exact historical blobs. Generated RULE-SET
        # manifests and workflows may legitimately advance after the release;
        # validate_release_manifest proves each pinned blob remains reachable
        # at its declared path instead of requiring it to equal today's blob.
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

        config_pin = manifest["implementation_pins"]["config_baseline"]
        policy = json.loads((ROOT / "sources/policy.json").read_text(encoding="utf-8"))
        self.assertEqual(config_pin["git_blob_sha"], policy["managed_config_guard"]["approved_git_blob_sha"])
        self.assertEqual(config_pin["path"], policy["managed_config_guard"]["path"])
        self.assertEqual(config_pin["access"], "read_only")

    def test_config_release_pin_must_match_owner_approved_baseline_not_working_tree(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
        config_pin = manifest["implementation_pins"]["config_baseline"]
        _validate_config_baseline_pin(ROOT, config_pin)
        with self.assertRaisesRegex(ValueError, "owner-approved"):
            _validate_config_baseline_pin(ROOT, {**config_pin, "git_blob_sha": "0" * 40})

    def _allowlisted_assessment_fixture(self):
        adapters = json.loads((ROOT / "automation/execution_adapters.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "automation/program_registry.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        program = next(item for item in registry["programs"] if item["id"] == "script_assess_sources")
        callers = ["workflow_automation_watchdog"]
        adapter["enabled"] = True
        adapter["allowed_callers"] = callers
        program["orchestration"] = {
            "enabled": True, "allowed_callers": callers,
            "max_attempts": 1, "timeout_seconds": 480,
        }
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
        source_path = adapter["entrypoint"]["path"]
        source_sha = subprocess.run(
            ["git", "hash-object", source_path], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        record = {
            "target_program_id": "script_assess_sources",
            "capability": "source_assessment",
            "release_id": manifest["release_id"],
            "adapter_entry_sha256": _canonical_digest(adapter),
            "registry_entry_sha256": _canonical_digest(program),
            "source_path": source_path,
            "source_git_blob_sha": source_sha,
            "allowed_callers": callers,
            "input_contract_sha256": _canonical_digest(adapter["input_contract"]),
            "output_contract_sha256": _canonical_digest(adapter["output_contract"]),
            "dependency_contract_sha256": _canonical_digest(adapter["dependency_contract"]),
            "resource_contract_sha256": _canonical_digest(adapter["resource_contract"]),
            "verifier_contract_sha256": _canonical_digest(adapter["completion"]["artifact_verifier"]),
        }
        policy = {"schema_version": 1, "default_decision": "deny", "allowed_adapters": [record]}
        return policy, adapters, registry, manifest["release_id"]

    def test_empty_default_deny_allowlist_rejects_enabled_python_adapter(self):
        adapters = json.loads((ROOT / "automation/execution_adapters.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "automation/program_registry.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "script_assess_sources")
        adapter["enabled"] = True
        with self.assertRaisesRegex(ValueError, "enabled Python adapters and exact release allowlist differ"):
            _validate_python_adapter_policy(
                ROOT, {"schema_version": 1, "default_decision": "deny", "allowed_adapters": []},
                adapters, registry, "shadowrocket-automation-baseline-2026.11.04.9",
            )

    def test_exact_capability_allowlist_accepts_pinned_adapter_and_rejects_drift(self):
        policy, adapters, registry, release_id = self._allowlisted_assessment_fixture()
        self.assertEqual(_validate_python_adapter_policy(ROOT, policy, adapters, registry, release_id), 1)
        adapters["adapters"] = [
            dict(item) if item["target_program_id"] != "script_assess_sources"
            else {**item, "timeout_seconds": item["timeout_seconds"] + 1}
            for item in adapters["adapters"]
        ]
        with self.assertRaisesRegex(ValueError, "adapter entry digest does not match"):
            _validate_python_adapter_policy(ROOT, policy, adapters, registry, release_id)

    def test_unknown_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                validate_release_manifest(root, manifest)


if __name__ == "__main__":
    unittest.main()
