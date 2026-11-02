import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from lifecycle_audit import inspect, protected, rid, deletion_confirmed


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
        for domain in ("api.google.com","login.microsoft.com","cdn.apple.com","foo.aliyun.com","api.tencent.com","img.bytedance.com"):
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

    def test_intervening_dns_recovery_breaks_deletion_confirmation(self):
        history=[
            {"checked_at":"2026-11-01T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"},
            {"checked_at":"2026-11-15T00:00:00+00:00","status":"DNS_EXISTS_OR_NODATA"},
            {"checked_at":"2026-12-15T00:00:00+00:00","status":"CONFIRMED_NXDOMAIN_OBSERVATION"}
        ]
        self.assertFalse(deletion_confirmed(history))

    def test_deletion_ids_are_stable_and_policy_specific(self):
        self.assertEqual(rid("DIRECT","DOMAIN,api.example"),rid("DIRECT","DOMAIN,api.example"))
        self.assertNotEqual(rid("DIRECT","DOMAIN,api.example"),rid("PROXY","DOMAIN,api.example"))


if __name__=="__main__":
    unittest.main()
