import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_external_intelligence_catalog import validate_catalog

class ExternalIntelligenceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "sources/external_intelligence_catalog.json").read_text(encoding="utf-8"))

    def test_catalog_is_valid_and_non_activating(self):
        self.assertEqual(validate_catalog(self.data), [])
        self.assertTrue(all(x["activation"] in {"never_from_catalog", "candidate_only", "evidence_only"} for x in self.data["providers"]))

    def test_rejects_untrusted_endpoint(self):
        data = json.loads(json.dumps(self.data))
        data["providers"][0]["endpoint"] = "https://evil.example/feed"
        self.assertTrue(any("HTTPS provider allowlist" in error for error in validate_catalog(data)))

    def test_rejects_duplicate_ids(self):
        data = json.loads(json.dumps(self.data))
        data["providers"].append(dict(data["providers"][0]))
        self.assertTrue(any("unique" in error for error in validate_catalog(data)))

    def test_preserves_user_config_boundary(self):
        data = json.loads(json.dumps(self.data))
        data["required_future_controls"] = [x for x in data["required_future_controls"] if "modules/uu.conf" not in x]
        self.assertTrue(any("immutability boundary" in error for error in validate_catalog(data)))

if __name__ == "__main__":
    unittest.main()
