import hashlib
import importlib.util
import json
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


    def test_task_retry_reuses_the_same_bounded_batch_for_same_predecessor(self):
        assessor = load_assessor()
        items = [{"url": f"https://raw.githubusercontent.com/o/r/main/{n}.list"} for n in range(23)]
        predecessor = {"workflow_run_id": "41870001234", "artifact_sha256": "a" * 64}
        first = assessor.rotate_assessment_urls_for_task(items, predecessor, 20)
        retry = assessor.rotate_assessment_urls_for_task(items, predecessor, 20)
        self.assertEqual(first, retry)
        self.assertEqual(len(first), 20)
        self.assertEqual(len({item["url"] for item in first}), 20)

    def test_task_batch_rejects_unbound_or_malformed_predecessor(self):
        assessor = load_assessor()
        items = [{"url": "https://raw.githubusercontent.com/o/r/main/a.list"}]
        with self.assertRaisesRegex(ValueError, "workflow_run_id"):
            assessor.rotate_assessment_urls_for_task(items, {"workflow_run_id": "bad", "artifact_sha256": "a" * 64}, 1)
        with self.assertRaisesRegex(ValueError, "artifact digest"):
            assessor.rotate_assessment_urls_for_task(items, {"workflow_run_id": "123", "artifact_sha256": "bad"}, 1)

    def test_candidate_urls_are_deduplicated_and_seeded_first(self):
        assessor = load_assessor()
        candidates = [
            {"repository": "o/r", "stars": 10, "seeded_source_urls": ["https://raw.githubusercontent.com/o/r/main/seed.list"], "rule_list_urls": ["https://raw.githubusercontent.com/o/r/main/z.list", "https://raw.githubusercontent.com/o/r/main/seed.list", "https://raw.githubusercontent.com/o/r/main/z.list"]},
            {"repository": "o/s", "stars": 20, "rule_list_urls": ["https://raw.githubusercontent.com/o/s/main/a.list"]},
        ]
        flattened = assessor.flatten_candidate_urls(candidates)
        self.assertEqual([x["url"] for x in flattened], [
            "https://raw.githubusercontent.com/o/r/main/seed.list",
            "https://raw.githubusercontent.com/o/s/main/a.list",
            "https://raw.githubusercontent.com/o/r/main/z.list",
        ])
        self.assertEqual(len({x["url"] for x in flattened}), 3)

    def test_candidate_urls_round_robin_repositories_and_filter_metadata(self):
        assessor = load_assessor()
        candidates = [
            {"repository": "a/r", "stars": 1, "rule_list_urls": [
                "https://raw.githubusercontent.com/a/r/main/requirements.txt",
                "https://raw.githubusercontent.com/a/r/main/clash-rules/one.txt",
                "https://raw.githubusercontent.com/a/r/main/clash-rules/two.txt",
            ]},
            {"repository": "b/r", "stars": 2, "rule_list_urls": ["https://raw.githubusercontent.com/b/r/main/blocklist.txt"]},
            {"repository": "c/r", "stars": 3, "rule_list_urls": ["https://raw.githubusercontent.com/c/r/main/rules.list"]},
        ]
        flattened = assessor.flatten_candidate_urls(candidates)
        self.assertEqual({item["repository"] for item in flattened[:3]}, {"a/r", "b/r", "c/r"})
        self.assertNotIn("requirements.txt", " ".join(item["url"] for item in flattened))
        self.assertEqual(flattened[3]["repository"], "a/r")

    def test_task_batch_uses_cursor_skips_assessed_urls_and_rechecks_stale_parser_results(self):
        assessor = load_assessor()
        items = [
            {"repository": "a/r", "url": "https://raw.githubusercontent.com/a/r/main/clash-rules/a1.txt"},
            {"repository": "b/r", "url": "https://raw.githubusercontent.com/b/r/main/clash-rules/b1.txt"},
            {"repository": "c/r", "url": "https://raw.githubusercontent.com/c/r/main/clash-rules/c1.txt"},
            {"repository": "a/r", "url": "https://raw.githubusercontent.com/a/r/main/clash-rules/a2.txt"},
            {"repository": "b/r", "url": "https://raw.githubusercontent.com/b/r/main/clash-rules/b2.txt"},
            {"repository": "c/r", "url": "https://raw.githubusercontent.com/c/r/main/clash-rules/c2.txt"},
        ]
        predecessor = {"workflow_run_id": "41870001234", "artifact_sha256": "a" * 64}
        previous = {
            "https://raw.githubusercontent.com/a/r/main/clash-rules/a1.txt": {"parser_candidate": "domain-only", "parser_version": 2},
            "https://raw.githubusercontent.com/b/r/main/clash-rules/b1.txt": {"parser_candidate": "unsupported_or_too_small", "parser_version": 1},
        }
        batch = assessor.rotate_assessment_urls_for_task(items, predecessor, 3, cursor_url="https://raw.githubusercontent.com/a/r/main/clash-rules/a1.txt", previous_by_url=previous)
        self.assertEqual([item["url"] for item in batch], [
            "https://raw.githubusercontent.com/b/r/main/clash-rules/b1.txt",
            "https://raw.githubusercontent.com/c/r/main/clash-rules/c1.txt",
            "https://raw.githubusercontent.com/a/r/main/clash-rules/a2.txt",
        ])
        self.assertEqual(len({item["repository"] for item in batch}), 3)

    def test_assessment_progress_restores_verified_prior_checkpoint_cursor(self):
        assessor = load_assessor()
        url = "https://raw.githubusercontent.com/o/r/main/rules.list"
        result = {"url": url, "parser_candidate": "clash-domain-rules", "parser_version": 2, "sha256": "a" * 64}
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        result_sha = hashlib.sha256(encoded).hexdigest()
        artifact_sha = "b" * 64
        queue = {"tasks": [{
            "task_id": "prior-task", "target_program_id": "script_assess_sources",
            "input": {"predecessor": {"workflow_run_id": "123456789", "artifact_sha256": artifact_sha}},
            "assessment_checkpoint": {
                "schema_version": 1, "batch_id": "discovery-run:123456789:" + artifact_sha[:12],
                "predecessor_artifact_sha256": artifact_sha,
                "completed": {url: {"result": result, "result_sha256": result_sha}},
                "last_successful_url": url, "updated_at": "2026-11-07T12:48:00Z",
            },
        }]}
        cursor, restored = assessor.assessment_progress_from_queue(queue, current_task_id="current-task")
        self.assertEqual(cursor, url)
        self.assertEqual(restored[url], result)

    def test_assessment_progress_rejects_checkpoint_digest_mismatch(self):
        assessor = load_assessor()
        url = "https://raw.githubusercontent.com/o/r/main/rules.list"
        artifact_sha = "b" * 64
        queue = {"tasks": [{
            "task_id": "prior-task", "target_program_id": "script_assess_sources",
            "input": {"predecessor": {"workflow_run_id": "123456789", "artifact_sha256": artifact_sha}},
            "assessment_checkpoint": {
                "schema_version": 1, "batch_id": "discovery-run:123456789:" + artifact_sha[:12],
                "predecessor_artifact_sha256": artifact_sha,
                "completed": {url: {"result": {"url": url}, "result_sha256": "0" * 64}},
                "last_successful_url": url, "updated_at": "2026-11-07T12:48:00Z",
            },
        }]}
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            assessor.assessment_progress_from_queue(queue, current_task_id="current-task")

    def test_clash_yaml_payload_is_parsed_as_domain_rules(self):
        assessor = load_assessor()
        rows = [f"  - {chr(39)}DOMAIN-SUFFIX,example{i}.com{chr(39)}" for i in range(25)]
        payload = ("payload:\n" + "\n".join(rows)).encode("utf-8")
        result = assessor.assess_payload(payload, "https://raw.githubusercontent.com/o/r/main/clash-rules/domains.txt", [])
        self.assertEqual(result["parser_candidate"], "clash-domain-rules")
        self.assertEqual(result["clash_yaml_rule_lines"], 25)
        self.assertEqual(result["suffix_domain_count"], 25)
        self.assertEqual(result["parser_version"], 2)
        self.assertFalse(result["activation_eligible"])

    def test_parser_cache_requires_matching_content_hash_and_policy_claims(self):
        assessor = load_assessor()
        previous = {
            "sha256": "a" * 64,
            "readme_policy_claims": ["DIRECT"],
            "parser_candidate": "domain-only",
            "parser_version": 2,
        }
        self.assertTrue(assessor.assessment_cache_hit(previous, "a" * 64, ["DIRECT"]))
        self.assertFalse(assessor.assessment_cache_hit(dict(previous, parser_version=1), "a" * 64, ["DIRECT"]))
        self.assertFalse(assessor.assessment_cache_hit(previous, "b" * 64, ["DIRECT"]))
        self.assertFalse(assessor.assessment_cache_hit(previous, "a" * 64, ["PROXY"]))
        self.assertFalse(assessor.assessment_cache_hit({"error": "offline"}, "a" * 64, ["DIRECT"]))


if __name__ == "__main__":
    unittest.main()
