import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import discover_sources


class ExternalIntelligenceCatalogTests(unittest.TestCase):
    def catalog_copy(self):
        return json.loads(discover_sources.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_is_valid_and_non_activating(self):
        catalog = discover_sources.load_external_intelligence_catalog()
        self.assertEqual(len(catalog["providers"]), 8)
        self.assertTrue(all(item["activation"] in {"never_from_catalog", "candidate_only", "evidence_only"} for item in catalog["providers"]))

    def test_catalog_rejects_duplicate_provider_ids(self):
        data = self.catalog_copy()
        data["providers"].append(dict(data["providers"][0]))
        with self.assertRaisesRegex(ValueError, "unique"):
            discover_sources.validate_external_intelligence_catalog(data)

    def test_catalog_rejects_unapproved_endpoint(self):
        data = self.catalog_copy()
        data["providers"][0]["endpoint"] = "https://untrusted.example/feed"
        with self.assertRaisesRegex(ValueError, "allowlist"):
            discover_sources.validate_external_intelligence_catalog(data)

    def test_catalog_rejects_non_https_endpoint(self):
        data = self.catalog_copy()
        data["providers"][0]["endpoint"] = "http://github.com/example"
        with self.assertRaisesRegex(ValueError, "allowlist"):
            discover_sources.validate_external_intelligence_catalog(data)

    def test_catalog_rejects_credentials_and_nonstandard_ports(self):
        for endpoint in ("https://user:pass@github.com/example", "https://github.com:8443/example"):
            with self.subTest(endpoint=endpoint):
                data = self.catalog_copy()
                data["providers"][0]["endpoint"] = endpoint
                with self.assertRaisesRegex(ValueError, "allowlist"):
                    discover_sources.validate_external_intelligence_catalog(data)

    def test_catalog_rejects_invalid_activation(self):
        data = self.catalog_copy()
        data["providers"][0]["activation"] = "automatic_production"
        with self.assertRaisesRegex(ValueError, "activation"):
            discover_sources.validate_external_intelligence_catalog(data)

    def test_catalog_endpoints_use_https_allowlist(self):
        data = self.catalog_copy()
        for item in data["providers"]:
            self.assertTrue(item["endpoint"].startswith("https://"))
            self.assertIn(item["endpoint"].split("/")[2], discover_sources.CATALOG_ALLOWED_HOSTS)


if __name__ == "__main__":
    unittest.main()
