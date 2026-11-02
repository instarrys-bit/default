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
    def test_discovery_search_scope_is_expanded_and_bounded(self):
        discovery = load_script("discover_sources")
        self.assertGreaterEqual(len(discovery.QUERIES), 25)
        self.assertGreaterEqual(discovery.MAX_REPOS_PER_QUERY, 50)
        self.assertGreaterEqual(discovery.MAX_README_REPOSITORIES, 100)
        self.assertIn("Apple services domain list", discovery.QUERIES)
        self.assertIn("malware phishing domain blocklist", discovery.QUERIES)
        self.assertIn("China app domains list", discovery.QUERIES)

    def test_assessment_capacity_is_expanded_but_bounded(self):
        assessment = load_script("assess_sources")
        self.assertGreaterEqual(assessment.MAX_URLS, 200)
        self.assertLessEqual(assessment.MAX_URLS, 500)


if __name__ == "__main__":
    unittest.main()
