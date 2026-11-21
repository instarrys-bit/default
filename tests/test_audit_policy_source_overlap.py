from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_policy_source_overlap import build_report


class PolicySourceOverlapUnavailableFeedTests(unittest.TestCase):
    def setUp(self):
        self.assessments = {
            "assessments": [{
                "id": "removed-feed",
                "repository": "example/policy",
                "policy_candidate": "REJECT",
                "parser_candidate": "domain-only",
                "url": "https://raw.githubusercontent.com/example/policy/main/list.txt",
            }]
        }

    def test_permanently_missing_feed_is_recorded_and_skipped(self):
        def fetcher(url, repository):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        report = build_report(self.assessments, fetcher=fetcher)

        self.assertEqual(report["audit_status"], "partial")
        self.assertEqual(report["feed_count"], 0)
        self.assertEqual(report["unavailable_feed_count"], 1)
        self.assertEqual(report["unavailable_feeds"][0]["http_status"], 404)
        self.assertEqual(report["unavailable_feeds"][0]["repository"], "example/policy")
        self.assertEqual(report["activation_count"], 0)

    def test_gone_feed_is_recorded_and_skipped(self):
        def fetcher(url, repository):
            raise urllib.error.HTTPError(url, 410, "Gone", {}, None)

        report = build_report(self.assessments, fetcher=fetcher)

        self.assertEqual(report["audit_status"], "partial")
        self.assertEqual(report["unavailable_feeds"][0]["http_status"], 410)

    def test_valid_feed_is_still_analyzed(self):
        report = build_report(
            self.assessments,
            fetcher=lambda url, repository: b"example.com\n",
        )

        self.assertEqual(report["audit_status"], "complete")
        self.assertEqual(report["feed_count"], 1)
        self.assertEqual(report["unavailable_feed_count"], 0)

    def test_unexpected_http_error_remains_fail_closed(self):
        def fetcher(url, repository):
            raise urllib.error.HTTPError(url, 503, "Unavailable", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            build_report(self.assessments, fetcher=fetcher)


if __name__ == "__main__":
    unittest.main()
