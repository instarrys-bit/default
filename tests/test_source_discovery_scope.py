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
        self.assertFalse(any("apple" in query.lower() for query in discovery.QUERIES))


    def test_tree_scans_rotate_unscanned_and_failed_repositories_first(self):
        discovery = load_script("discover_sources")
        inventory = {
            "owner/recent": {"stars": 10, "tree_scanned_at": "2026-11-02T00:00:00+00:00", "tree_scan_status": "complete"},
            "owner/never-a": {"stars": 1},
            "owner/failed": {"stars": 0, "tree_scanned_at": "2026-11-01T00:00:00+00:00", "tree_scan_status": "error"},
            "owner/never-b": {"stars": 20},
            "owner/old": {"stars": 5, "tree_scanned_at": "2026-10-01T00:00:00+00:00", "tree_scan_status": "complete"},
        }
        selected = discovery.select_tree_scan_repositories(inventory, 3)
        self.assertEqual([name for name, _ in selected], [
            "owner/never-b", "owner/never-a", "owner/failed"
        ])
        next_batch = discovery.select_tree_scan_repositories(inventory, 2)
        self.assertEqual([name for name, _ in next_batch], [
            "owner/never-b", "owner/never-a"
        ])

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
    def test_assessment_read_and_review_capacity_is_high(self):
        assessment = load_script("assess_sources")
        self.assertGreaterEqual(assessment.MAX_URLS, 5_000)
        self.assertGreaterEqual(assessment.MAX_TOTAL_BYTES, 250_000_000)
        self.assertGreaterEqual(assessment.MAX_BYTES, 5_000_000)

if __name__ == "__main__":
    unittest.main()
