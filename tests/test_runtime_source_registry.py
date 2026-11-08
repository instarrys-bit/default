import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_domains import source_registry_path


class RuntimeSourceRegistryTests(unittest.TestCase):
    def test_default_registry_remains_the_fixed_production_registry(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(source_registry_path(), ROOT / "sources/domain_sources.json")

    def test_runtime_registry_is_accepted_only_inside_runner_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner_temp = Path(temporary)
            registry = runner_temp / "source-activation" / "sources" / "domain_sources.json"
            registry.parent.mkdir(parents=True)
            registry.write_text('{"sources": [], "scoring": {}}', encoding="utf-8")
            with patch.dict(os.environ, {
                "RUNNER_TEMP": str(runner_temp),
                "SHADOWROCKET_SOURCE_REGISTRY": str(registry),
            }, clear=True):
                self.assertEqual(source_registry_path(), registry.resolve())

    def test_runtime_registry_outside_runner_temp_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            registry = Path(outside) / "domain_sources.json"
            registry.write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {
                "RUNNER_TEMP": temporary,
                "SHADOWROCKET_SOURCE_REGISTRY": str(registry),
            }, clear=True):
                with self.assertRaisesRegex(ValueError, "inside RUNNER_TEMP"):
                    source_registry_path()

    def test_runtime_override_requires_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry = Path(temporary) / "missing.json"
            with patch.dict(os.environ, {
                "RUNNER_TEMP": temporary,
                "SHADOWROCKET_SOURCE_REGISTRY": str(registry),
            }, clear=True):
                with self.assertRaises(FileNotFoundError):
                    source_registry_path()


if __name__ == "__main__":
    unittest.main()
