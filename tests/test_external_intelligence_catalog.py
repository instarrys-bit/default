import json
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import discover_sources


class ExternalIntelligenceCatalogTests(unittest.TestCase):
    def catalog_copy(self):
        return json.loads(discover_sources.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_is_valid_and_non_activating(self):
        catalog = discover_sources.load_external_intelligence_catalog()
        self.assertEqual(len(catalog["providers"]), 10)
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


    def test_openphish_parser_emits_typed_non_policy_observations(self):
        provider = self.catalog_copy()["providers"][2]
        records = discover_sources.parse_openphish_payload(
            b"https://login-example.test/signin\nnot-a-url\n", provider, provider["endpoint"]
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["data_type"], "phishing_url")
        self.assertEqual(records[0]["metadata"]["host"], "login-example.test")
        self.assertNotIn("policy", records[0])
        self.assertEqual(len(records[0]["record_sha256"]), 64)

    def test_urlhaus_parser_skips_comments_and_preserves_typed_url_evidence(self):
        provider = self.catalog_copy()["providers"][1]
        payload = b"# comment\n1,2026-11-06 10:00:00,https://bad.example/payload,online,malware_download\n"
        records = discover_sources.parse_urlhaus_payload(payload, provider, "https://urlhaus.abuse.ch/downloads/csv_recent/")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["data_type"], "malware_url")
        self.assertEqual(records[0]["source_timestamp"], "2026-11-06 10:00:00")
        self.assertEqual(records[0]["metadata"]["host"], "bad.example")

    def test_iana_parser_emits_registry_type_not_routing_policy(self):
        provider = self.catalog_copy()["providers"][5]
        records = discover_sources.parse_iana_payload(
            b'<a href="/domains/root/db/com.html">COM</a><a href="/domains/root/db/net.html">NET</a>',
            provider, provider["endpoint"]
        )
        self.assertEqual([x["value"] for x in records], ["com", "net"])
        self.assertTrue(all(x["data_type"] == "tld_registry" and "policy" not in x for x in records))

    def test_ct_and_ripe_parsers_keep_distinct_observation_types(self):
        providers = self.catalog_copy()["providers"]
        ct = discover_sources.parse_ct_payload(
            b'[{"name_value":"*.example.com\\nwww.example.net","not_before":"2026-11-01"}]',
            providers[3], "https://crt.sh/?q=example.com&output=json"
        )
        ripe = discover_sources.parse_ripestat_payload(
            b'{"data":{"prefix":"192.0.2.0/24","name":"Example Net","type":"prefix"}}',
            providers[4], "https://stat.ripe.net/data/network-info/data.json?resource=192.0.2.0/24"
        )
        self.assertEqual({x["value"] for x in ct}, {"example.com", "www.example.net"})
        self.assertEqual(ct[0]["data_type"], "certificate_name")
        self.assertEqual(ripe[0]["data_type"], "network_infrastructure")

    def test_repository_search_parser_accepts_only_provider_host(self):
        provider = self.catalog_copy()["providers"][6]
        payload = b'[{"path_with_namespace":"group/rules","web_url":"https://gitlab.com/group/rules","star_count":12}]'
        records = discover_sources.parse_repository_search_payload(payload, provider, provider["endpoint"], "gitlab.com")
        self.assertEqual(records[0]["data_type"], "repository_metadata")
        self.assertEqual(records[0]["value"], "group/rules")
        self.assertEqual(discover_sources.parse_repository_search_payload(
            b'[{"path_with_namespace":"group/rules","web_url":"https://evil.example/group/rules"}]',
            provider, provider["endpoint"], "gitlab.com"
        ), [])

    def test_provider_redirect_handler_blocks_cross_host_redirect(self):
        handler = discover_sources.ProviderRedirectHandler("openphish.com")
        request = urllib.request.Request("https://openphish.com/feed.txt")
        with self.assertRaisesRegex(ValueError, "redirect escaped"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://attacker.example/feed")

    def test_external_fetch_rejects_hosts_not_in_provider_allowlist(self):
        with self.assertRaisesRegex(ValueError, "outside its provider HTTPS boundary"):
            discover_sources.fetch_external_payload("https://attacker.example/feed", "attacker.example")
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            discover_sources.ProviderRedirectHandler("attacker.example")


if __name__ == "__main__":
    unittest.main()
