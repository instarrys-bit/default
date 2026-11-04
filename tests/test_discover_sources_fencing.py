import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discover_sources


class DiscoverSourcesFencingTests(unittest.TestCase):
    def test_persisted_document_and_report_require_their_live_resource_leases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "sources" / "discovered_sources.json"
            report = root / "reports" / "source-discovery.md"
            data = {"candidate_count": 0, "candidates": []}
            with patch.object(discover_sources, "OUTPUT", output), \
                 patch.object(discover_sources, "REPORT", report), \
                 patch.object(discover_sources, "write_document") as write_document, \
                 patch.object(discover_sources, "assert_resource_lease_from_environment") as assert_lease:
                discover_sources.persist_discovery_outputs(data)
            write_document.assert_called_once_with(
                output, data, "candidates", lease_required=True
            )
            assert_lease.assert_called_once_with("reports/source-discovery.md")
            self.assertTrue(report.is_file())

    def test_fatal_discovery_error_returns_nonzero_and_preserves_previous_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "sources" / "discovered_sources.json"
            report = root / "reports" / "source-discovery.md"
            summary = root / "step-summary.md"
            output.parent.mkdir(parents=True)
            previous = {"candidate_count": 1, "candidates": [
                {"repository": "trusted/previous", "html_url": "https://github.com/trusted/previous"}
            ]}
            output.write_text(json.dumps(previous), encoding="utf-8")
            with patch.object(discover_sources, "OUTPUT", output), \
                 patch.object(discover_sources, "REPORT", report), \
                 patch.object(discover_sources, "request_json", side_effect=OSError("GitHub API unavailable")), \
                 patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_TOKEN": ""}, clear=True):
                result = discover_sources.main()
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), previous)
            self.assertIn("Source discovery warning", summary.read_text(encoding="utf-8"))
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
