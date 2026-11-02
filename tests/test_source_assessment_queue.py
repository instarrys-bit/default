import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_assessor():
    path = ROOT / "scripts" / "assess_sources.py"
    spec = importlib.util.spec_from_file_location("assess_sources", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssessmentQueueTests(unittest.TestCase):
    def test_cursor_rotates_across_batches_without_repeating_within_a_batch(self):
        assessor = load_assessor()
        items = [{"url": f"https://raw.githubusercontent.com/o/r/main/{n}.list"} for n in range(7)]
        first = assessor.rotate_assessment_urls(items, None, 3)
        second = assessor.rotate_assessment_urls(items, first[-1]["url"], 3)
        third = assessor.rotate_assessment_urls(items, second[-1]["url"], 3)
        self.assertEqual([x["url"] for x in first], [x["url"] for x in items[:3]])
        self.assertEqual([x["url"] for x in second], [x["url"] for x in items[3:6]])
        self.assertEqual([x["url"] for x in third], [x["url"] for x in items[6:7]] + [x["url"] for x in items[:2]])
        self.assertEqual(len({x["url"] for x in first + second}), 6)

    def test_cursor_restarts_safely_when_previous_url_disappears(self):
        assessor = load_assessor()
        items = [{"url": "a"}, {"url": "b"}, {"url": "c"}]
        self.assertEqual(assessor.rotate_assessment_urls(items, "missing", 2), items[:2])

    def test_candidate_urls_are_deduplicated_and_seeded_first(self):
        assessor = load_assessor()
        candidates = [
            {"repository": "o/r", "stars": 10, "seeded_source_urls": ["seed"], "rule_list_urls": ["z", "seed", "z"]},
            {"repository": "o/s", "stars": 20, "rule_list_urls": ["a"]},
        ]
        flattened = assessor.flatten_candidate_urls(candidates)
        self.assertEqual([x["url"] for x in flattened], ["seed", "z", "a"])
        self.assertEqual(len({x["url"] for x in flattened}), 3)

    def test_parser_cache_requires_matching_content_hash_and_policy_claims(self):
        assessor = load_assessor()
        previous = {
            "sha256": "a" * 64,
            "readme_policy_claims": ["DIRECT"],
            "parser_candidate": "domain-only",
        }
        self.assertTrue(assessor.assessment_cache_hit(previous, "a" * 64, ["DIRECT"]))
        self.assertFalse(assessor.assessment_cache_hit(previous, "b" * 64, ["DIRECT"]))
        self.assertFalse(assessor.assessment_cache_hit(previous, "a" * 64, ["PROXY"]))
        self.assertFalse(assessor.assessment_cache_hit({"error": "offline"}, "a" * 64, ["DIRECT"]))


if __name__ == "__main__":
    unittest.main()
