import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from audit_policy_source_overlap import extract_domains, build_report

class PolicySourceOverlapTests(unittest.TestCase):
    def test_domain_only_parser_ignores_keywords_and_ip_rules(self):
        payload=b"""
DOMAIN,api.example.com
DOMAIN-SUFFIX,example.org,DIRECT
DOMAIN-KEYWORD,example
IP-CIDR,192.0.2.0/24
HOST-SUFFIX,qx.example,OUTSIDE
"""
        self.assertEqual(extract_domains(payload),{"api.example.com","example.org","qx.example"})

    def test_same_publisher_files_are_unioned_not_counted_twice(self):
        data={"assessments":[
            {"policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","repository":"a/rules","url":"u1"},
            {"policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","repository":"a/rules","url":"u2"},
            {"policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","repository":"b/rules","url":"u3"},
            {"policy_candidate":"PROXY","parser_candidate":"shadowrocket-domain-rules","repository":"c/rules","url":"u4"}
        ]}
        payloads={"u1":b"one.example\n","u2":b"two.example\n","u3":b"two.example\n","u4":b"one.example\n"}
        result=build_report(data,lambda url,repo:payloads[url])
        self.assertEqual(result["publisher_counts"]["DIRECT"],2)
        self.assertEqual(result["overlaps"][0]["overlap_count"],1)
        self.assertEqual(result["cross_policy_conflict_domain_count"],1)
        self.assertEqual(result["activation_count"],0)

if __name__=="__main__": unittest.main()
