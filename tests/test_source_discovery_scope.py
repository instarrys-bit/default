import importlib.util
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
        self.assertGreaterEqual(discovery.MAX_README_REPOSITORIES, 1_500)
        self.assertGreaterEqual(discovery.MAX_SEARCH_PAGES, 10)
        self.assertGreaterEqual(discovery.MAX_TREE_REPOSITORIES, 500)
        self.assertGreaterEqual(discovery.MAX_TREE_SCAN_WORKERS, 2)
        self.assertGreaterEqual(discovery.MAX_TREE_ENTRIES_PER_REPOSITORY, 3_000)
        self.assertGreaterEqual(discovery.MAX_README_BYTES, 1_000_000)
        self.assertIn("open source domain ruleset", discovery.QUERIES)
        self.assertTrue(callable(discovery.discover_tree_urls))
        self.assertIn("GitHub domain list repository", discovery.QUERIES)
        self.assertIn("MetaCubeX meta-rules-dat", discovery.QUERIES)
        self.assertIn("AdGuardTeam AdGuardFilters", discovery.QUERIES)
        self.assertIn("hagezi dns-blocklists", discovery.QUERIES)
        self.assertIn("国内域名规则", discovery.QUERIES)
        self.assertIn("开源分流规则", discovery.QUERIES)
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
        self.assertIn('discovery_revision="$(git rev-parse HEAD:scripts/discover_sources.py | cut -c1-12)"', watchdog)
        self.assertIn('base_key="source-discovery:$discovery_day:$discovery_revision"', watchdog)


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

if __name__ == "__main__":
    unittest.main()
