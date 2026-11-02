import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from deterministic_review import evidence_gate

class CorrelatedEvidenceGateTests(unittest.TestCase):
    def test_high_overlap_publishers_are_one_effective_group(self):
        evidence=[
            {"source_id":"a","publisher":"one/rules","lineage_status":"unverified","currently_listed":True},
            {"source_id":"b","publisher":"two/rules","lineage_status":"verified","currently_listed":True},
        ]
        result=evidence_gate(evidence,{"a":0.4,"b":0.4},2,0.8,(),{("one/rules","two/rules")})
        self.assertEqual(len(result[2]),2)
        self.assertEqual(len(result[3]),1)
        self.assertFalse(result[4])

    def test_unknown_lineage_without_correlation_is_not_a_veto(self):
        evidence=[
            {"source_id":"a","publisher":"one/rules","lineage_status":"unverified","currently_listed":True},
            {"source_id":"b","publisher":"two/rules","lineage_status":"partial","currently_listed":True},
        ]
        self.assertTrue(evidence_gate(evidence,{"a":0.4,"b":0.4},2,0.8,())[-1])

if __name__=="__main__": unittest.main()
