import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assess_sources import load_task_options


class AssessmentPredecessorTests(unittest.TestCase):
    def write_payload(self, workflow_name):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "task-input.json"
        path.write_text(json.dumps({
            "max_urls": 20,
            "max_file_bytes": 1000000,
            "max_total_bytes": 10000000,
            "predecessor": {
                "program_id": "script_discover_sources",
                "workflow_name": workflow_name,
                "workflow_run_id": "41900000000",
                "workflow_head_sha": "a" * 40,
                "artifact_path": "sources/discovered_sources.json",
                "artifact_sha256": "b" * 64,
            },
        }), encoding="utf-8")
        return directory, path

    def test_accepts_only_dedicated_discovery_workflow_predecessor(self):
        directory, path = self.write_payload("Shadowrocket Source Discovery (Watchdog)")
        try:
            options = load_task_options(path)
            self.assertEqual(options["predecessor"]["workflow_name"], "Shadowrocket Source Discovery (Watchdog)")
        finally:
            directory.cleanup()

    def test_rejects_monolithic_audit_as_discovery_predecessor(self):
        directory, path = self.write_payload("Shadowrocket Deterministic Domain Audit (User Config Baseline)")
        try:
            with self.assertRaisesRegex(ValueError, "dedicated discovery workflow"):
                load_task_options(path)
        finally:
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
