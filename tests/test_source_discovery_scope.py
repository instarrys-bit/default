import importlib.util
import json
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceDiscoveryScopeTests(unittest.TestCase):
    def test_discovery_search_scope_is_broad_bilingual_and_bounded(self):
        discovery = load_script("discover_sources")
        self.assertGreaterEqual(len(discovery.QUERIES), 80)
        self.assertGreaterEqual(discovery.MAX_REPOS_PER_QUERY, 100)
        self.assertGreaterEqual(discovery.MAX_README_REPOSITORIES, 2_500)
        self.assertGreaterEqual(discovery.MAX_SEARCH_PAGES, 10)
        self.assertGreaterEqual(discovery.MAX_TREE_REPOSITORIES, 750)
        self.assertGreaterEqual(discovery.MAX_TREE_SCAN_WORKERS, 2)
        self.assertGreaterEqual(discovery.MAX_TREE_ENTRIES_PER_REPOSITORY, 5_000)
        self.assertGreaterEqual(discovery.MAX_README_BYTES, 1_000_000)
        self.assertIn("open source domain ruleset", discovery.QUERIES)
        self.assertTrue(callable(discovery.discover_tree_urls))
        self.assertIn("GitHub domain list repository", discovery.QUERIES)
        self.assertIn("MetaCubeX meta-rules-dat", discovery.QUERIES)
        self.assertIn("AdGuardTeam AdGuardFilters", discovery.QUERIES)
        self.assertIn("hagezi dns-blocklists", discovery.QUERIES)
        self.assertIn("国内域名规则", discovery.QUERIES)
        self.assertIn("开源分流规则", discovery.QUERIES)
        self.assertIn("RPZ domain reputation feeds", discovery.QUERIES)
        self.assertIn("mobile application domain list Android iOS", discovery.QUERIES)
        self.assertIn("恶意软件命令控制域名情报", discovery.QUERIES)
        self.assertIn("AdguardTeam/HostlistsRegistry", discovery.SEED_SOURCE_URLS)
        self.assertIn("StevenBlack/hosts", discovery.SEED_SOURCE_URLS)
        self.assertIn("easylist/easyprivacy", discovery.SEED_SOURCE_URLS)
        self.assertIn("Surge domain-set direct proxy reject rules", discovery.QUERIES)
        self.assertIn("China DNS accelerated domain list", discovery.QUERIES)
        self.assertIn("Chinese adblock domain rules AdRules", discovery.QUERIES)
        self.assertIn("Loyalsoldier/surge-rules", discovery.SEED_SOURCE_URLS)
        self.assertIn("felixonmars/dnsmasq-china-list", discovery.SEED_SOURCE_URLS)
        self.assertIn("Cats-Team/AdRules", discovery.SEED_SOURCE_URLS)
        self.assertIn("QuixoticHeart/rule-set", discovery.SEED_SOURCE_URLS)
        self.assertIn("MetaCubeX/meta-rules-dat", discovery.SEED_SOURCE_URLS)
        self.assertEqual(
            discovery.SEED_SOURCE_URLS["Loyalsoldier/surge-rules"],
            [
                "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/direct.txt",
                "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/proxy.txt",
                "https://raw.githubusercontent.com/Loyalsoldier/surge-rules/release/reject.txt",
            ],
        )
        self.assertFalse(any("apple" in query.lower() for query in discovery.QUERIES))
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        policy = (ROOT / "scripts" / "source_handoff_policy.py").read_text(encoding="utf-8")
        self.assertIn("def discovery_pipeline_revision", policy)
        self.assertIn('"scripts/discover_sources.py"', policy)
        self.assertIn('".github/workflows/source-discovery.yml"', policy)
        self.assertIn("from source_handoff_policy import discovery_pipeline_revision", watchdog)
        self.assertIn("print(discovery_pipeline_revision(Path.cwd()))", watchdog)
        self.assertIn('base_key="source-discovery:$discovery_day:$discovery_revision"', watchdog)


    def test_fortune_rankings_produce_exactly_100_provenanced_enterprise_targets(self):
        discovery = load_script("discover_sources")
        html = "<table>" + "".join(
            f"<tr><td>{rank}</td><td>Company {rank}</td></tr>" for rank in range(1, 101)
        ) + "</table>"
        provider = {
            "id": "fortune-global-500", "provider": "Fortune", "ranking_id": "fortune-global-500",
            "ranking_year": 2026, "rank_column": 0, "company_column": 1,
            "region": "Global", "ranking_basis": "annual revenue", "activation": "evidence_only",
        }
        records = discovery.parse_fortune_rankings(html.encode(), provider, "https://fortune.com/ranking/global500/")
        self.assertEqual(len(records), 100)
        self.assertEqual(records[0]["value"], "Company 1")
        self.assertEqual(records[-1]["metadata"]["rank"], 100)
        self.assertEqual(records[0]["data_type"], "enterprise_ranked_entity")
        self.assertEqual(records[0]["activation"], "evidence_only")

    def test_enterprise_company_queries_rotate_with_stable_cursor_and_no_policy_effect(self):
        discovery = load_script("discover_sources")
        observations = []
        for ranking_id, region in (("fortune-china-500", "China"), ("fortune-global-500", "Global")):
            for rank in range(1, 101):
                observations.append({
                    "data_type": "enterprise_ranked_entity", "value": f"{ranking_id} Company {rank}",
                    "metadata": {"ranking_id": ranking_id, "ranking_year": 2026, "rank": rank, "region": region},
                })
        intel = {"observations": observations}
        first = discovery.build_enterprise_search_batch(intel, {}, batch_size=20)
        second = discovery.build_enterprise_search_batch(intel, {
            "enterprise_search_cursor": first["cursor_next"],
            "enterprise_search_fingerprint": first["fingerprint"],
        }, batch_size=20)
        self.assertEqual(first["target_count"], 200)
        self.assertEqual(len(first["jobs"]), 20)
        self.assertEqual(len(second["jobs"]), 20)
        self.assertEqual(first["cursor_next"], second["cursor_start"])
        self.assertTrue(set(x["company"] for x in first["jobs"]).isdisjoint(
            set(x["company"] for x in second["jobs"])
        ))
        self.assertTrue(all(x["scope"] == "enterprise_top100" for x in first["jobs"]))

    def test_enterprise_rankings_are_registered_as_evidence_only_providers(self):
        discovery = load_script("discover_sources")
        catalog = discovery.load_external_intelligence_catalog()
        providers = {x["id"]: x for x in catalog["providers"]}
        self.assertEqual(providers["fortune-china-500"]["activation"], "evidence_only")
        self.assertEqual(providers["fortune-global-500"]["activation"], "evidence_only")
        self.assertEqual(providers["fortune-china-500"]["company_column"], 2)
        self.assertEqual(providers["fortune-global-500"]["company_column"], 1)

    def test_tree_scans_rotate_unscanned_and_failed_repositories_first(self):
        discovery = load_script("discover_sources")
        inventory = {
            "owner/recent": {"stars": 10, "tree_scanned_at": "2026-11-02T00:00:00+00:00", "tree_scan_status": "complete", "updated_at": "rev1", "tree_scanned_updated_at": "rev1", "default_branch": "main", "tree_scanned_default_branch": "main"},
            "owner/never-a": {"stars": 1},
            "owner/failed": {"stars": 0, "tree_scanned_at": "2026-11-01T00:00:00+00:00", "tree_scan_status": "error"},
            "owner/never-b": {"stars": 20},
            "owner/old": {"stars": 5, "tree_scanned_at": "2026-10-01T00:00:00+00:00", "tree_scan_status": "complete", "updated_at": "rev0", "tree_scanned_updated_at": "rev0", "default_branch": "main", "tree_scanned_default_branch": "main"},
        }
        selected = discovery.select_tree_scan_repositories(inventory, 3)
        self.assertEqual([name for name, _ in selected], [
            "owner/never-b", "owner/never-a", "owner/failed"
        ])
        next_batch = discovery.select_tree_scan_repositories(inventory, 2)
        self.assertEqual([name for name, _ in next_batch], [
            "owner/never-b", "owner/never-a"
        ])


    def test_tree_scan_inventory_includes_old_repositories_and_retries_truncated_trees(self):
        discovery = load_script("discover_sources")
        existing = {"candidates": [
            {"repository": "owner/old", "stars": 5, "tree_scanned_at": "2026-10-01T00:00:00+00:00", "tree_scan_status": "complete", "rule_list_urls": ["old.list"]},
            {"repository": "owner/truncated", "stars": 4, "tree_scanned_at": "2026-10-02T00:00:00+00:00", "tree_scan_status": "truncated", "rule_list_urls": ["partial.list"]},
        ]}
        current = {
            "owner/new": {"repository": "owner/new", "stars": 10, "rule_list_urls": ["new.list"]},
            "owner/old": {"repository": "owner/old", "stars": 6, "rule_list_urls": ["fresh.list"]},
        }
        inventory = discovery.merge_tree_scan_inventory(existing, current)
        self.assertEqual(set(inventory), {"owner/old", "owner/truncated", "owner/new"})
        self.assertEqual(set(inventory["owner/old"]["rule_list_urls"]), {"old.list", "fresh.list"})
        selected = discovery.select_tree_scan_repositories(inventory, 2)
        self.assertEqual([name for name, _ in selected], ["owner/new", "owner/truncated"])

    def test_tree_scan_inventory_includes_old_repositories_and_retries_truncated_trees(self):
        discovery = load_script("discover_sources")
        existing = {"candidates": [
            {"repository": "owner/old", "stars": 5, "tree_scanned_at": "2026-10-01T00:00:00+00:00", "tree_scan_status": "complete", "rule_list_urls": ["old.list"]},
            {"repository": "owner/truncated", "stars": 4, "tree_scanned_at": "2026-10-02T00:00:00+00:00", "tree_scan_status": "truncated", "rule_list_urls": ["partial.list"]},
        ]}
        current = {
            "owner/new": {"repository": "owner/new", "stars": 10, "rule_list_urls": ["new.list"]},
            "owner/old": {"repository": "owner/old", "stars": 6, "rule_list_urls": ["fresh.list"]},
        }
        inventory = discovery.merge_tree_scan_inventory(existing, current)
        self.assertEqual(set(inventory), {"owner/old", "owner/truncated", "owner/new"})
        self.assertEqual(set(inventory["owner/old"]["rule_list_urls"]), {"old.list", "fresh.list"})
        selected = discovery.select_tree_scan_repositories(inventory, 2)
        self.assertEqual([name for name, _ in selected], ["owner/new", "owner/truncated"])

    def test_github_api_rate_limit_retry_uses_retry_after_or_reset(self):
        discovery = load_script("discover_sources")
        self.assertEqual(discovery.api_retry_delay({"Retry-After": "7"}, 0, now=100), 7.0)
        self.assertEqual(discovery.api_retry_delay({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "112"}, 0, now=100), 12.0)
        self.assertEqual(discovery.api_retry_delay({}, 2, now=100), 8.0)

    def test_tree_discovery_filters_paths_and_reports_truncation(self):
        discovery = load_script("discover_sources")
        tree = {
            "truncated": True,
            "tree": [
                {"type": "blob", "path": "rules/direct.list", "size": 100},
                {"type": "blob", "path": "rules/adult/blocked.txt", "size": 100},
                {"type": "blob", "path": "rules/oversized.conf", "size": 6_000_000},
                {"type": "blob", "path": "README.md", "size": 100},
                {"type": "tree", "path": "rules/nested"},
            ],
        }
        with patch.object(discovery, "request_json", return_value=tree):
            urls, truncated = discovery.discover_tree_urls("owner", "repo", "main", "token")
        self.assertEqual(urls, ["https://raw.githubusercontent.com/owner/repo/main/rules/direct.list"])
        self.assertTrue(truncated)
    def test_assessment_batches_are_bounded_and_rotation_covers_inventory(self):
        assessment = load_script("assess_sources")
        self.assertEqual(assessment.MAX_URLS, 20)
        self.assertEqual(assessment.MAX_TOTAL_BYTES, 10_000_000)
        self.assertEqual(assessment.MAX_BYTES, 1_000_000)
        inventory = [{"url": f"https://raw.githubusercontent.com/owner/repo/main/{i}.list"} for i in range(45)]
        first = assessment.rotate_assessment_urls(inventory, None, assessment.MAX_URLS)
        second = assessment.rotate_assessment_urls(inventory, first[-1]["url"], assessment.MAX_URLS)
        third = assessment.rotate_assessment_urls(inventory, second[-1]["url"], assessment.MAX_URLS)
        self.assertEqual(len(first), 20)
        self.assertEqual(len(second), 20)
        self.assertEqual(len(third), 20)
        self.assertEqual(len({item["url"] for item in first + second + third}), 45)

    def test_completed_tree_scan_is_skipped_until_repository_revision_changes(self):
        discovery = load_script("discover_sources")
        inventory = {
            "owner/unchanged": {
                "stars": 3, "tree_scanned_at": "2026-11-02T00:00:00+00:00",
                "tree_scan_status": "complete", "updated_at": "rev1",
                "tree_scanned_updated_at": "rev1", "default_branch": "main",
                "tree_scanned_default_branch": "main",
            },
            "owner/changed": {
                "stars": 2, "tree_scanned_at": "2026-11-02T00:00:00+00:00",
                "tree_scan_status": "complete", "updated_at": "rev2",
                "tree_scanned_updated_at": "rev1", "default_branch": "main",
                "tree_scanned_default_branch": "main",
            },
        }
        self.assertEqual([name for name, _ in discovery.select_tree_scan_repositories(inventory, 10)], ["owner/changed"])

    def test_readme_snapshot_reuses_same_repository_revision(self):
        discovery = load_script("discover_sources")
        repo = {"full_name": "owner/repo", "default_branch": "main", "updated_at": "rev1"}
        previous = {
            "default_branch": "main", "updated_at": "rev1", "readme_sha256": "a" * 64,
            "readme_rule_list_urls": ["cached.list"], "readme_policy_claims": {"cached.list": ["DIRECT"]},
        }
        with patch.object(discovery, "fetch_readme", side_effect=AssertionError("unexpected README fetch")):
            readme, digest, urls, claims, cached = discovery.readme_snapshot(repo, previous)
        self.assertEqual(readme, "")
        self.assertEqual(digest, "a" * 64)
        self.assertEqual(urls, ["cached.list"])
        self.assertEqual(claims, {"cached.list": ["DIRECT"]})
        self.assertTrue(cached)


    def test_discovery_and_assessment_share_one_fenced_supervision_lease(self):
        document = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        adapters = {item["target_program_id"]: item for item in document["adapters"]}
        key = "logical/source-dag-supervision"
        discovery = adapters["workflow_source_discovery"]["resource_contract"]
        assessment = adapters["script_assess_sources"]["resource_contract"]
        self.assertIn(key, discovery["resource_keys"])
        self.assertIn(key, assessment["resource_keys"])
        self.assertEqual(discovery["lease_seconds"], assessment["lease_seconds"])
        self.assertEqual(discovery["lease_seconds"], 3600)
        self.assertIs(discovery["fencing_required"], True)
        self.assertIs(assessment["fencing_required"], True)
        self.assertEqual(adapters["workflow_source_discovery"]["write_resources"], [])
        self.assertEqual(adapters["script_assess_sources"]["write_resources"], [])

if __name__ == "__main__":
    unittest.main()
