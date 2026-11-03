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

    def test_unknown_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema_version"):
                validate_release_manifest(root, manifest)


if __name__ == "__main__":
    unittest.main()
