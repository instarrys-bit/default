import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_release_manifest import validate_release_manifest


class ReleaseManifestSmokeTests(unittest.TestCase):
    def test_repository_manifest_passes(self):
        result = validate_release_manifest(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["verified_git_blob_pins"], 6)
        self.assertEqual(result["independent_python_dispatch"], "blocked")


    def test_release_pins_match_current_repository_inputs(self):
        manifest = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))

        def blob_sha(relative_path):
            import subprocess
            return subprocess.run(
                ["git", "hash-object", relative_path],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        for item in manifest["component_schemas"].values():
            self.assertEqual(item["git_blob_sha"], blob_sha(item["path"]), item["path"])

        for name in ("watchdog_workflow", "production_workflow", "config_baseline"):
            item = manifest["implementation_pins"][name]
            self.assertEqual(item["git_blob_sha"], blob_sha(item["path"]), item["path"])

        self.assertEqual(manifest["implementation_pins"]["config_baseline"]["access"], "read_only")

    def test_unknown_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                validate_release_manifest(root, manifest)


if __name__ == "__main__":
    unittest.main()
