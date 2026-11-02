import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from lifecycle_audit import inspect, protected, rid, deletion_confirmed, scope_intersects_rule
import lifecycle_audit
import json
import tempfile
import os


class LifecycleAuditSafetyTests(unittest.TestCase):
    @patch("lifecycle_audit.query", return_value=3)
    def test_requires_both_resolvers_and_both_record_families_to_return_nxdomain(self, mocked):
        result=inspect("expired.example")
        self.assertEqual(result["status"],"CONFIRMED_NXDOMAIN_OBSERVATION")
        self.assertEqual(mocked.call_count,4)

    @patch("lifecycle_audit.query", side_effect=[3,3,0,3])
    def test_nodata_or_existing_answer_prevents_deletion(self, mocked):
        self.assertEqual(inspect("mail-only.example")["status"],"DNS_EXISTS_OR_NODATA")

    @patch("lifecycle_audit.query", return_value=None)
    def test_resolver_failure_is_unknown_not_invalid(self, mocked):
        self.assertEqual(inspect("unreachable.example")["status"],"UNKNOWN_OR_RESOLVER_ERROR")

    def test_major_company_suffixes_are_protected(self):
        config={"protected_exact":[],"protected_suffixes":[]}
        for domain in ("api.google.com","login.microsoft.com","cdn.apple.com","foo.aliyun.com","api.tencent.com","img.bytedance.com","api.huawei.com","static.jd.com","cdn.xiaohongshu.com","api.alipay.com","api.tencentcloud.com","api.pingan.com"):
            self.assertTrue(protected(domain,config),domain)

    def test_one_nxdomain_observation_never_deletes(self):
        history=[{"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}]
        self.assertFalse(deletion_confirmed(history))

    def test_two_nxdomain_observations_need_at_least_30_days(self):
        short=[
            {"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-11-30T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
        ]
        enough=[
            {"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-12-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
        ]
        self.assertFalse(deletion_confirmed(short))
        self.assertTrue(deletion_confirmed(enough))

    def test_daily_confirmations_accumulate_over_30_days(self):
        history=[
            {"checked_at":f"2026-11-{day:02d}T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
            for day in range(1, 31)
        ]
        history.append({"checked_at":"2026-12-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"})
        self.assertTrue(deletion_confirmed(history))

    def test_recovery_anywhere_in_history_breaks_deletion_confirmation(self):
        history=[
            {"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-11-15T00:00:00+00:00","status":"DNS_EXISTS_OR_NODATA"},
            {"checked_at":"2026-12-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-12-02T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
        ]
        self.assertFalse(deletion_confirmed(history))

    def test_intervening_dns_recovery_breaks_deletion_confirmation(self):
        history=[
            {"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-11-15T00:00:00+00:00","status":"DNS_EXISTS_OR_NODATA"},
            {"checked_at":"2026-12-15T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
        ]
        self.assertFalse(deletion_confirmed(history))


    def test_restore_id_works_without_waiting_for_lifecycle_due_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rules=root/"rulesets"
            (root/"sources").mkdir()
            rules.mkdir()
            for policy in ("direct","proxy","reject"):
                (rules/(policy+".list")).write_text("",encoding="utf-8")
            (rules/"lifecycle_state.json").write_text(json.dumps({
                "due_milestones":[],"monthly_review_due":False,"published_rule_count":0
            }),encoding="utf-8")
            (rules/"deletion_archive.json").write_text(json.dumps({"items":[{
                "id":"restore-me","policy":"direct","rule":"DOMAIN,old.example","domain":"old.example",
                "removed_at":"2026-10-01T00:00:00+00:00"
            }]}),encoding="utf-8")
            (rules/"pending_queue.json").write_text(json.dumps({"items":[]}),encoding="utf-8")
            (root/"sources/protected_domains.json").write_text(json.dumps({
                "protected_exact":[],"protected_suffixes":[]
            }),encoding="utf-8")
            with patch.object(lifecycle_audit,"ROOT",root), patch.object(lifecycle_audit,"DIR",rules), patch.object(lifecycle_audit,"REPORT",root/"reports/lifecycle"), patch.dict(os.environ,{"LIFECYCLE_RESTORE_IDS":"restore-me"}), patch("lifecycle_audit.inspect",side_effect=AssertionError("restore-only must not run DNS deletion checks")):
                lifecycle_audit.main()
            self.assertIn("DOMAIN,old.example",(rules/"direct.list").read_text(encoding="utf-8"))
            saved=json.loads((rules/"deletion_archive.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(saved["items"][0].get("restored_at"))

    def test_restore_refuses_cross_policy_published_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rules=root/"rulesets"
            (root/"sources").mkdir()
            rules.mkdir()
            (rules/"direct.list").write_text("DOMAIN,old.example\n",encoding="utf-8")
            (rules/"proxy.list").write_text("",encoding="utf-8")
            (rules/"reject.list").write_text("",encoding="utf-8")
            (rules/"lifecycle_state.json").write_text(json.dumps({
                "due_milestones":[],"monthly_review_due":False,"published_rule_count":1
            }),encoding="utf-8")
            (rules/"deletion_archive.json").write_text(json.dumps({"items":[{
                "id":"restore-proxy","policy":"proxy","rule":"DOMAIN,old.example","domain":"old.example","removed_at":"2026-10-01T00:00:00+00:00"
            }]}),encoding="utf-8")
            (rules/"pending_queue.json").write_text(json.dumps({"items":[]}),encoding="utf-8")
            (root/"sources/protected_domains.json").write_text(json.dumps({
                "protected_exact":[],"protected_suffixes":[]
            }),encoding="utf-8")
            with patch.object(lifecycle_audit,"ROOT",root), patch.object(lifecycle_audit,"DIR",rules), patch.object(lifecycle_audit,"REPORT",root/"reports/lifecycle"), patch.dict(os.environ,{"LIFECYCLE_RESTORE_IDS":"restore-proxy"}), patch("lifecycle_audit.inspect",side_effect=AssertionError("restore-only must not run DNS deletion checks")):
                lifecycle_audit.main()
            self.assertEqual((rules/"proxy.list").read_text(encoding="utf-8"),"")
            report=json.loads((root/"reports/lifecycle/latest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["restore_refused"]),1)
            archive=json.loads((rules/"deletion_archive.json").read_text(encoding="utf-8"))
            self.assertIsNone(archive["items"][0].get("restored_at"))

    def test_lifecycle_deletes_only_after_30_day_confirmation_and_keeps_protected_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rules=root/"rulesets"
            (root/"sources").mkdir()
            rules.mkdir()
            (rules/"direct.list").write_text("DOMAIN,expired.example\nDOMAIN,api.google.com\n",encoding="utf-8")
            for policy in ("proxy","reject"):
                (rules/(policy+".list")).write_text("",encoding="utf-8")
            state={"due_milestones":[5000],"monthly_review_due":False,"published_rule_count":5000}
            (rules/"lifecycle_state.json").write_text(json.dumps(state),encoding="utf-8")
            identity=rid("DIRECT","DOMAIN,expired.example")
            (rules/"lifecycle_observations.json").write_text(json.dumps({"items":{
                identity:{"history":[{"checked_at":"2026-10-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}]}
            }}),encoding="utf-8")
            (rules/"deletion_archive.json").write_text(json.dumps({"items":[]}),encoding="utf-8")
            (rules/"pending_queue.json").write_text(json.dumps({"items":[]}),encoding="utf-8")
            (root/"sources/protected_domains.json").write_text(json.dumps({
                "protected_exact":[],"protected_suffixes":[]
            }),encoding="utf-8")
            with patch.object(lifecycle_audit,"ROOT",root), patch.object(lifecycle_audit,"DIR",rules), patch.object(lifecycle_audit,"REPORT",root/"reports/lifecycle"), patch.dict(os.environ,{"LIFECYCLE_RESTORE_IDS":""}), patch("lifecycle_audit.inspect",return_value={"status":"CONFIRMED_NXDOMAIN_OBSERVATION","resolver_status":{"cloudflare_A":3,"cloudflare_AAAA":3,"google_A":3,"google_AAAA":3}}), patch("lifecycle_gate.complete_lifecycle_review",return_value=state):
                lifecycle_audit.main()
            direct=(rules/"direct.list").read_text(encoding="utf-8")
            self.assertNotIn("DOMAIN,expired.example",direct)
            self.assertIn("DOMAIN,api.google.com",direct)
            archive=json.loads((rules/"deletion_archive.json").read_text(encoding="utf-8"))
            self.assertEqual(len(archive["items"]),1)
            self.assertEqual(archive["items"][0]["first_confirmed_at"],"2026-10-01T00:00:00+00:00")

    def test_due_lifecycle_run_reaches_completion_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            rules=root/"rulesets"
            (root/"sources").mkdir()
            rules.mkdir()
            (rules/"direct.list").write_text("DOMAIN,old.example\n",encoding="utf-8")
            for policy in ("proxy","reject"):
                (rules/(policy+".list")).write_text("",encoding="utf-8")
            state={"due_milestones":[5000],"monthly_review_due":False,"published_rule_count":5000}
            (rules/"lifecycle_state.json").write_text(json.dumps(state),encoding="utf-8")
            (rules/"pending_queue.json").write_text(json.dumps({"items":[]}),encoding="utf-8")
            (root/"sources/protected_domains.json").write_text(json.dumps({
                "protected_exact":[],"protected_suffixes":[]
            }),encoding="utf-8")
            with patch.object(lifecycle_audit,"ROOT",root), patch.object(lifecycle_audit,"DIR",rules), patch.object(lifecycle_audit,"REPORT",root/"reports/lifecycle"), patch.dict(os.environ,{"LIFECYCLE_RESTORE_IDS":""}), patch("lifecycle_audit.inspect",return_value={"status":"DNS_EXISTS_OR_NODATA","resolver_status":{}}), patch("lifecycle_gate.complete_lifecycle_review",return_value=state) as complete:
                lifecycle_audit.main()
            complete.assert_called_once()

    def test_restore_overlap_detection_covers_exact_and_suffix_scopes(self):
        self.assertTrue(scope_intersects_rule("DOMAIN-SUFFIX,example.com","DOMAIN,api.example.com"))
        self.assertTrue(scope_intersects_rule("DOMAIN-SUFFIX,example.com","DOMAIN-SUFFIX,sub.example.com"))
        self.assertFalse(scope_intersects_rule("DOMAIN,api.example.com","DOMAIN,mail.example.com"))
        self.assertFalse(scope_intersects_rule("DOMAIN,invalid_domain","DOMAIN,invalid_domain"))

    def test_deletion_ids_are_stable_and_policy_specific(self):
        self.assertEqual(rid("DIRECT","DOMAIN,api.example"),rid("DIRECT","DOMAIN,api.example"))
        self.assertNotEqual(rid("DIRECT","DOMAIN,api.example"),rid("PROXY","DOMAIN,api.example"))


if __name__=="__main__":
    unittest.main()
