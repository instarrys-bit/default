import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_ruleset_config_conflicts import classify_rule, sync
from audit_ruleset_config_overlap import all_rule_lines, parse_skip_proxy


def make_root(root, config, direct="", proxy="", reject="", queue=None):
    (root / "modules").mkdir()
    (root / "rulesets").mkdir()
    (root / "reports").mkdir()
    (root / "modules" / "uu.conf").write_text(config, encoding="utf-8")
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
        return classify_rule(policy, line, all_rule_lines(config), parse_skip_proxy(config))

    def test_exact_different_policy_is_removed(self):
        result = self.classify("DIRECT", "DOMAIN,api.example.com", ["DOMAIN,api.example.com,PROXY"])
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["effective_policy"])
        self.assertIn("[PROXY]", result["config_rule"])

    def test_exact_same_policy_scope_overlap_is_removed(self):
        result = self.classify("DIRECT", "DOMAIN,api.example.com", ["DOMAIN,api.example.com,DIRECT"])
        self.assertEqual(result["status"], "CONFLICT")
        self.assertIsNone(result["effective_policy"])

    def test_parent_suffix_is_retained_when_config_has_exact_child_exception(self):
        result = self.classify(
            "DIRECT", "DOMAIN-SUFFIX,example.com",
            ["DOMAIN,api.example.com,REJECT"],
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_parent_suffix_is_retained_when_config_has_child_suffix_exception(self):
        result = self.classify(
            "DIRECT", "DOMAIN-SUFFIX,example.com",
            ["DOMAIN-SUFFIX,api.example.com,REJECT"],
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_parent_suffix_is_removed_when_config_suffix_covers_full_scope(self):
        result = self.classify(
            "DIRECT", "DOMAIN-SUFFIX,example.com",
            ["DOMAIN-SUFFIX,example.com,DIRECT"],
        )
        self.assertEqual(result["status"], "CONFLICT")

    def test_skip_proxy_conflicts_with_proxy_and_reject(self):
        proxy = self.classify("PROXY", "DOMAIN,api.example.com", [], "*.example.com")
        reject = self.classify("REJECT", "DOMAIN,api.example.com", [], "*.example.com")
        direct = self.classify("DIRECT", "DOMAIN,api.example.com", [], "*.example.com")
        self.assertEqual(proxy["status"], "CONFLICT")
        self.assertEqual(reject["status"], "CONFLICT")
        self.assertEqual(direct["status"], "CONFLICT")

    def test_keyword_overlap_is_not_evaluated_or_deleted(self):
        result = self.classify(
            "DIRECT", "DOMAIN,api.example.com",
            ["DOMAIN-KEYWORD,example,PROXY"],
        )
        self.assertEqual(result["status"], "NO_CONFLICT")

    def test_scope_coverage_checks_all_config_rules_without_ordering(self):
        config = config_with_rules([]).replace(
            "RULE-SET,https://example.invalid/reject.list,REJECT",
            "RULE-SET,https://example.invalid/reject.list,REJECT" + chr(10) + "DOMAIN,api.example.com,PROXY",
        )
        rules = all_rule_lines(config)
        self.assertIn((6, "DOMAIN,api.example.com,PROXY"), rules)
        result = classify_rule("DIRECT", "DOMAIN,api.example.com", rules, [])
        self.assertEqual(result["status"], "CONFLICT")

    def test_config_change_without_conflict_leaves_rule_sets_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            direct_before = "DOMAIN,keep.example.com\n"
            proxy_before = "DOMAIN-SUFFIX,foreign.example.net\n"
            reject_before = "DOMAIN,ad.example.org\n"
            make_root(
                root,
                config_with_rules(["DOMAIN-SUFFIX,unrelated.example.com,PROXY"]),
                direct=direct_before,
                proxy=proxy_before,
                reject=reject_before,
            )
            report = sync(root=root, now="2026-11-02T00:00:00+00:00")
            self.assertEqual(report["removed_count"], 0)
            self.assertEqual(report["retained_for_review_count"], 0)
            self.assertEqual((root / "rulesets" / "direct.list").read_text(), direct_before)
            self.assertEqual((root / "rulesets" / "proxy.list").read_text(), proxy_before)
            self.assertEqual((root / "rulesets" / "reject.list").read_text(), reject_before)
            self.assertFalse((root / "rulesets" / "config_conflict_archive.json").exists())


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

    def test_reject_config_suffix_removes_covered_rules_from_all_rule_sets_and_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = {
                "schema_version": 1,
                "max_published_rules": 30000,
                "queued_count": 1,
                "items": [{
                    "policy": "PROXY", "scope": "exact_candidate",
                    "domain": "queued.example.com", "queued_at": "2026-11-02T00:00:00Z"
                }]
            }
            make_root(
                root,
                config_with_rules(["DOMAIN-SUFFIX,example.com,REJECT"]),
                direct="DOMAIN,api.example.com\n",
                proxy="DOMAIN,web.example.com\n",
                reject="DOMAIN,ads.example.com\n",
                queue=queue,
            )
            report = sync(root=root, now="2026-11-03T00:00:00+00:00")
            self.assertEqual(report["published_removed_count"], 3)
            self.assertEqual(report["pending_queue_removed_count"], 1)
            for policy in ("direct", "proxy", "reject"):
                self.assertEqual((root / "rulesets" / f"{policy}.list").read_text(), "")
            archive = json.loads((root / "rulesets" / "config_conflict_archive.json").read_text())
            self.assertEqual(len(archive["items"]), 4)
            self.assertTrue(all(item["config_sha256"] for item in archive["items"]))
            self.assertEqual(report["config_sha256"], archive["items"][0]["config_sha256"])

    def test_sync_retains_parent_direct_when_config_has_exact_reject_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = "DOMAIN-SUFFIX,example.com\n"
            make_root(
                root,
                config_with_rules(["DOMAIN,api.example.com,REJECT"]),
                direct=parent,
            )
            report = sync(root=root, now="2026-11-02T00:00:00+00:00")
            self.assertEqual(report["published_removed_count"], 0)
            self.assertEqual((root / "rulesets" / "direct.list").read_text(), parent)
            self.assertFalse((root / "rulesets" / "config_conflict_archive.json").exists())

    def test_old_archive_entry_is_superseded_when_current_config_no_longer_overlaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(root, config_with_rules([]))
            archive_path = root / "rulesets" / "config_conflict_archive.json"
            archive_path.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "id": "cfg-old-entry",
                    "policy": "PROXY",
                    "rule": "DOMAIN,api.example.com",
                    "domain": "api.example.com",
                    "scope": "exact_candidate",
                    "origin": "published_ruleset",
                    "removed_at": "2026-10-01T00:00:00+00:00",
                    "config_blob_sha": "old-config-sha",
                    "restored_at": None
                }]
            }), encoding="utf-8")
            report = sync(root=root, now="2026-11-02T00:00:00+00:00")
            saved = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(report["active_archive_count"], 0)
            self.assertEqual(saved["items"][0]["superseded_at"], "2026-11-02T00:00:00+00:00")
            self.assertIn("no longer overlaps", saved["items"][0]["superseded_reason"])

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

    def test_restore_refuses_cross_policy_overlap_and_reports_selectable_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(root, config_with_rules([]), direct="DOMAIN-SUFFIX,example.com\n")
            archive_path = root / "rulesets" / "config_conflict_archive.json"
            archive_path.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "id": "cfg-cross-policy",
                    "policy": "PROXY",
                    "rule": "DOMAIN,api.example.com",
                    "domain": "api.example.com",
                    "scope": "exact_candidate",
                    "origin": "published_ruleset",
                    "removed_at": "2026-10-01T00:00:00+00:00",
                    "config_blob_sha": "old-config-sha",
                    "restored_at": None
                }]
            }), encoding="utf-8")
            report = sync(root=root, restore_ids=["cfg-cross-policy"], now="2026-11-02T00:00:00+00:00")
            self.assertEqual(len(report["restored"]), 0)
            self.assertEqual(len(report["restore_refused"]), 1)
            self.assertEqual(report["restore_refused"][0]["reason"], "restoration would create a cross-policy overlap")
            self.assertEqual(report["restoration_option_count"], 1)
            self.assertEqual(report["restoration_options"][0]["id"], "cfg-cross-policy")
            self.assertIn("cfg-cross-policy", (root / "reports" / "ruleset-config-conflict-sync.md").read_text())
            self.assertEqual((root / "rulesets" / "proxy.list").read_text(encoding="utf-8"), "")

    def test_restore_succeeds_after_config_conflict_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(root, config_with_rules(["DOMAIN,api.example.com,PROXY"]), direct="DOMAIN,api.example.com\n")
            sync(root=root, now="2026-11-01T00:00:00+00:00")
            archive = json.loads((root / "rulesets" / "config_conflict_archive.json").read_text())
            item_id = archive["items"][0]["id"]
            (root / "modules" / "uu.conf").write_text(
                config_with_rules([]), encoding="utf-8"
            )
            restored = sync(root=root, restore_ids=[item_id], now="2026-11-02T00:00:00+00:00")
            self.assertEqual(len(restored["restored"]), 1)
            self.assertIn("DOMAIN,api.example.com", (root / "rulesets" / "direct.list").read_text())

    def test_config_rollback_releases_archived_rule_to_normal_builder_gate(self):
        from build_rulesets import previously_published_reject_rules

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_root(
                root,
                config_with_rules(["DOMAIN,ads.example.com,DIRECT"]),
                reject="DOMAIN,ads.example.com\n",
            )
            sync(root=root, now="2026-11-01T00:00:00+00:00")
            archive_path = root / "rulesets" / "config_conflict_archive.json"
            archived = json.loads(archive_path.read_text(encoding="utf-8"))
            self.assertEqual(len(archived["items"]), 1)
            self.assertEqual(archived["items"][0]["origin"], "published_ruleset")

            # Owner removes the covering config rule. The next sync pass
            # supersedes the conflict so the normal builder can reconsider it.
            (root / "modules" / "uu.conf").write_text(
                config_with_rules([]), encoding="utf-8"
            )
            sync(root=root, now="2026-11-02T00:00:00+00:00")
            archived = json.loads(archive_path.read_text(encoding="utf-8"))
            item = archived["items"][0]
            self.assertTrue(item.get("superseded_at"))
            self.assertFalse(item.get("restored_at"))

            # Prior published REJECT authorization survives; pending-only
            # REJECT entries do not gain authorization from the archive.
            authorized = previously_published_reject_rules(set(), archived)
            self.assertIn("DOMAIN,ads.example.com", authorized)
            pending = {"items": [{**item, "origin": "pending_queue"}]}
            self.assertNotIn(
                "DOMAIN,ads.example.com",
                previously_published_reject_rules(set(), pending),
            )

    def test_config_a_to_b_to_a_reconciles_archive_without_auto_restoring_rules(self):
        from build_rulesets import previously_published_reject_rules
        from production_intent import decide

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = {
                "schema_version": 1,
                "max_published_rules": 30000,
                "queued_count": 2,
                "items": [
                    {"policy": "DIRECT", "scope": "exact_candidate", "domain": "queued.example.com"},
                    {"policy": "REJECT", "scope": "exact_candidate", "domain": "queued-reject.example.com"},
                ],
            }
            config_a = config_with_rules([])
            config_b = config_with_rules([
                "DOMAIN,api.example.com,REJECT",
                "DOMAIN,web.example.com,REJECT",
                "DOMAIN,ads.example.com,REJECT",
                "DOMAIN,queued.example.com,REJECT",
                "DOMAIN,queued-reject.example.com,REJECT",
            ])
            make_root(
                root, config_a,
                direct="DOMAIN,api.example.com\n",
                proxy="DOMAIN,web.example.com\n",
                reject="DOMAIN,ads.example.com\n",
                queue=queue,
            )
            config_path = root / "modules" / "uu.conf"
            original_a = config_path.read_bytes()
            self.assertEqual(config_path.read_bytes(), original_a)

            config_path.write_text(config_b, encoding="utf-8")
            before_b = config_path.read_bytes()
            report_b = sync(root=root, now="2026-11-02T00:00:00+00:00")
            self.assertEqual(config_path.read_bytes(), before_b)
            self.assertEqual(report_b["published_removed_count"], 3)
            self.assertEqual(report_b["pending_queue_removed_count"], 2)
            for policy in ("direct", "proxy", "reject"):
                self.assertEqual((root / "rulesets" / f"{policy}.list").read_text(), "")
            queue_b = json.loads((root / "rulesets" / "pending_queue.json").read_text())
            self.assertEqual(queue_b["items"], [])
            archive_path = root / "rulesets" / "config_conflict_archive.json"
            archive_b = json.loads(archive_path.read_text())
            self.assertEqual(len(archive_b["items"]), 5)
            self.assertEqual(
                {item["origin"] for item in archive_b["items"]},
                {"published_ruleset", "pending_queue"},
            )

            config_path.write_text(config_a, encoding="utf-8")
            before_a = config_path.read_bytes()
            intent = decide(
                event="push",
                current_fingerprint="a" * 64,
                last_success_fingerprint="a" * 64,
                path_classification={
                    "status": "INPUT_CHANGED",
                    "production_input_changes": ["modules/uu.conf"],
                    "non_production_changes": [],
                    "unknown_changes": [],
                },
                last_success_at="2026-11-01T00:00:00+00:00",
                successful_fingerprints={"a" * 64, "b" * 64},
                revision="c" * 40,
            )
            self.assertEqual(intent["decision"], "INPUT_CHANGED")
            self.assertTrue(intent["should_produce"])
            self.assertEqual(intent["idempotency_key"], "production:input:" + "a" * 64 + ":" + "c" * 40)

            report_a = sync(root=root, now="2026-11-03T00:00:00+00:00")
            self.assertEqual(config_path.read_bytes(), before_a)
            self.assertEqual(report_a["active_archive_count"], 0)
            archive_a = json.loads(archive_path.read_text())
            self.assertTrue(all(item.get("superseded_at") for item in archive_a["items"]))
            self.assertTrue(all(not item.get("restored_at") for item in archive_a["items"]))

            for policy in ("direct", "proxy", "reject"):
                self.assertEqual((root / "rulesets" / f"{policy}.list").read_text(), "")
            authorized_rejects = previously_published_reject_rules(set(), archive_a)
            self.assertIn("DOMAIN,ads.example.com", authorized_rejects)
            self.assertNotIn("DOMAIN,queued-reject.example.com", authorized_rejects)


if __name__ == "__main__":
    unittest.main()
