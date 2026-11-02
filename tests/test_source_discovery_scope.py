import importlib.util
import unittest
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
        self.assertGreaterEqual(discovery.MAX_README_REPOSITORIES, 1_000)
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

    def test_assessment_read_and_review_capacity_is_high(self):
        assessment = load_script("assess_sources")
        self.assertGreaterEqual(assessment.MAX_URLS, 5_000)
        self.assertGreaterEqual(assessment.MAX_TOTAL_BYTES, 250_000_000)
        self.assertGreaterEqual(assessment.MAX_BYTES, 5_000_000)

if __name__ == "__main__":
    unittest.main()
