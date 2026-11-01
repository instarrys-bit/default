import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_ruleset_config_conflicts import classify_rule, sync
from audit_ruleset_config_overlap import prior_rule_lines, first_ruleset_line, parse_skip_proxy


def make_root(root, config, direct="", proxy="", reject="", queue=None):
    (root / "shadowrocket").mkdir()
    (root / "rulesets").mkdir()
    (root / "reports").mkdir()
    (root / "shadowrocket" / "ss.conf").write_text(config, encoding="utf-8")
    (root / "rulesets" / "direct.list").write_text(direct, encoding="utf-8")
    (root / "rulesets" / "proxy.list").write_text(proxy, encoding="utf-8")
    (root / "rulesets" / "reject.list").write_text(reject, encoding="utf-8")
    (root / "rulesets" / "pending_queue.json").write_text(
        json.dumps(queue or {"schema_version": 1, "max_published_rules": 30000, "queued_count": 0, "items": []}),
        encoding="utf-8",
    )


def config_with_rules(rules, skip_proxy=""):
    return (
        "[General]\nskip-proxy = " + skip_proxy + "\n"
        "[Rule]\n" + "\n".join(rules) + "\n"
        "RULE-SET,https://example.invalid/reject.list,REJECT\n"
        "RULE-SET,https://example.invalid/proxy.list,PROXY\n"
        "RULE-SET,https://example.invalid/direct.list,DIRECT\n"
        "GEOIP,CN,DIRECT\nFINAL,PROXY\n[Host]\n"
    )


class ConfigConflictSyncTests(unittest.TestCase):
    def classify(self, policy, line, rules, skip=""):
        config = config_with_rules(rules, skip)
        return classify_rule(policy, line, prior_rule_lines(config), parse_skip_proxy(config))

    def test_exact_different_policy_is_removed(self):
        result = self.classify("DIRECT", "DOMAIN,api.example.com", ["DOMAIN,api.example.com,PROXY"])
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["effective_policy"], "PROXY")

    def test_exact_same_policy_is_not_a_conflict(self):
        result = self.classify("DIRECT", "DOMAIN,api.example.com", ["DOMAIN,api.example.com,DIRECT"])
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_suffix_is_removed_when_descendant_has_conflicting_explicit_policy(self):
        result = self.classify(
            "DIRECT", "DOMAIN-SUFFIX,example.com",
            ["DOMAIN,api.example.com,PROXY"],
        )
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["effective_policy"], "PROXY")

    def test_skip_proxy_conflicts_with_proxy_and_reject(self):
        proxy = self.classify("PROXY", "DOMAIN,api.example.com", [], "*.example.com")
        reject = self.classify("REJECT", "DOMAIN,api.example.com", [], "*.example.com")
        direct = self.classify("DIRECT", "DOMAIN,api.example.com", [], "*.example.com")
        self.assertEqual(proxy["status"], "CONFLICT")
        self.assertEqual(reject["status"], "CONFLICT")
        self.assertEqual(direct["status"], "NO_CONFLICT")

    def test_keyword_overlap_is_retained_for_review_not_deleted(self):
        result = self.classify(
            "DIRECT", "DOMAIN,api.example.com",
            ["DOMAIN-KEYWORD,example,PROXY"],
        )
        self.assertEqual(result["status"], "REVIEW")

    def test_rules_after_first_ruleset_are_not_higher_priority(self):
        config = config_with_rules([]).replace(
            "RULE-SET,https://example.invalid/reject.list,REJECT",
            "RULE-SET,https://example.invalid/reject.list,REJECT" + chr(10) + "DOMAIN,api.example.com,PROXY",
        )
        rules = prior_rule_lines(config)
        self.assertEqual(first_ruleset_line(config), 5)
        self.assertEqual(len(rules), 0)
        result = classify_rule("DIRECT", "DOMAIN,api.example.com", rules, [])
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_sync_removes_published_and_queued_conflicts_and_archives_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = {
                "schema_version": 1,
                "max_published_rules": 30000,
                "queued_count": 1,
                "items": [{
                    "policy": "PROXY", "scope": "exact_candidate",
                    "domain": "queued.example.com", "queued_at": "2026-11-01T00:00:00Z"
                }]
            }
            make_root(
                root,
                config_with_rules([
                    "DOMAIN,api.example.com,PROXY",
                    "DOMAIN,queued.example.com,DIRECT",
                    "DOMAIN,keep.example.com,DIRECT",
                ]),
                direct="DOMAIN,api.example.com\nDOMAIN,keep.example.com\n",
                queue=queue,
            )
            report = sync(root=root, now="2026-11-01T00:00:00+00:00")
            direct = (root / "rulesets" / "direct.list").read_text()
            self.assertNotIn("api.example.com", direct)
            self.assertIn("keep.example.com", direct)
            saved_queue = json.loads((root / "rulesets" / "pending_queue.json").read_text())
            self.assertEqual(saved_queue["items"], [])
            archive = json.loads((root / "rulesets" / "config_conflict_archive.json").read_text())
            self.assertEqual(len(archive["items"]), 2)
            self.assertEqual(report["published_removed_count"], 1)
            self.assertEqual(report["pending_queue_removed_count"], 1)
            self.assertTrue(report["config_read_only"])

    def test_restore_is_refused_while_conflict_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(root, config_with_rules(["DOMAIN,api.example.com,PROXY"]), direct="DOMAIN,api.example.com\n")
            sync(root=root, now="2026-11-01T00:00:00+00:00")
            archive = json.loads((root / "rulesets" / "config_conflict_archive.json").read_text())
            item_id = archive["items"][0]["id"]
            second = sync(root=root, restore_ids=[item_id], now="2026-11-02T00:00:00+00:00")
            self.assertEqual(len(second["restored"]), 0)
            self.assertEqual(len(second["restore_refused"]), 1)

    def test_restore_succeeds_after_config_conflict_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(root, config_with_rules(["DOMAIN,api.example.com,PROXY"]), direct="DOMAIN,api.example.com\n")
            sync(root=root, now="2026-11-01T00:00:00+00:00")
            archive = json.loads((root / "rulesets" / "config_conflict_archive.json").read_text())
            item_id = archive["items"][0]["id"]
            (root / "shadowrocket" / "ss.conf").write_text(
                config_with_rules(["DOMAIN,api.example.com,DIRECT"]), encoding="utf-8"
            )
            restored = sync(root=root, restore_ids=[item_id], now="2026-11-02T00:00:00+00:00")
            self.assertEqual(len(restored["restored"]), 1)
            self.assertIn("DOMAIN,api.example.com", (root / "rulesets" / "direct.list").read_text())


if __name__ == "__main__":
    unittest.main()
