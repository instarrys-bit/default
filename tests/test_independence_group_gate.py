import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from deterministic_review import evidence_gate

class ConfiguredGroupGateTests(unittest.TestCase):
    def test_distinct_publishers_in_same_configured_group_are_not_independent(self):
        evidence=[
            {"source_id":"a","publisher":"one/rules","independence_group":"shared-group","lineage_status":"verified","currently_listed":True},
            {"source_id":"b","publisher":"two/rules","independence_group":"shared-group","lineage_status":"partial","currently_listed":True},
        ]
        result=evidence_gate(evidence,{"a":0.4,"b":0.4},2,0.8,())
        self.assertEqual(len(result[2]),2)
        self.assertEqual(len(result[3]),1)
        self.assertFalse(result[4])

if __name__=="__main__": unittest.main()
