from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "storage" / "v2"))
from incident_store import record_incident, resolve_incidents

def seed():
    return {"schema_version": 1, "revision": 1, "incidents": [], "events": []}

class IncidentStoreTests(unittest.TestCase):
    def test_record_creates_auditable_manual_intervention(self):
        doc, result = record_incident(seed(), workflow="config_validator", run_id="100", source_sha="a"*40,
            classification="TEST_FAILURE", event_id="failure-100", summary="test failed",
            run_url="https://github.com/example/run/100")
        self.assertTrue(result["changed"]); self.assertEqual(result["state"], "MANUAL_INTERVENTION")
        self.assertEqual(doc["revision"], 2); self.assertEqual(doc["incidents"][0]["incident_state"]["state"], "MANUAL_INTERVENTION")
    def test_duplicate_event_is_idempotent(self):
        args=dict(workflow="config_validator",run_id="100",source_sha="a"*40,classification="TEST_FAILURE",
            event_id="failure-100",summary="test failed",run_url="https://github.com/example/run/100")
        first,_=record_incident(seed(),**args); second,result=record_incident(first,**args)
        self.assertFalse(result["changed"]); self.assertEqual(second["revision"],first["revision"])
    def test_resolve_only_closes_older_matching_incidents_after_verification(self):
        doc,_=record_incident(seed(),workflow="config_validator",run_id="100",source_sha="a"*40,
            classification="TEST_FAILURE",event_id="failure-100",summary="test failed",run_url="https://github.com/example/run/100")
        doc,result=resolve_incidents(doc,workflow="config_validator",before_run_id="101",
            classifications=["TEST_FAILURE"],event_id="success-101",verification_url="https://github.com/example/run/101")
        self.assertEqual(result["resolved"],1); self.assertEqual(doc["incidents"][0]["lifecycle_status"],"RECOVERED")
        self.assertEqual(doc["incidents"][0]["incident_state"]["verification"]["url"],"https://github.com/example/run/101")
    def test_resolve_preserves_newer_incidents(self):
        doc,_=record_incident(seed(),workflow="config_validator",run_id="200",source_sha="b"*40,
            classification="TEST_FAILURE",event_id="failure-200",summary="new failure",run_url="https://github.com/example/run/200")
        doc,result=resolve_incidents(doc,workflow="config_validator",before_run_id="199",
            classifications=["TEST_FAILURE"],event_id="success-199",verification_url="https://github.com/example/run/199")
        self.assertEqual(result["resolved"],0); self.assertEqual(doc["incidents"][0]["lifecycle_status"],"MANUAL_INTERVENTION")
        self.assertEqual(doc["revision"], 3)  # record + audited resolve event
        self.assertEqual(doc["events"][-1]["operation"], "resolve")
    def test_resolve_does_not_close_unlisted_classifications(self):
        doc,_=record_incident(seed(),workflow="config_validator",run_id="100",source_sha="a"*40,
            classification="AGENT_FAILURE",event_id="agent-100",summary="agent failed",run_url="https://github.com/example/run/100")
        doc,result=resolve_incidents(doc,workflow="config_validator",before_run_id="101",
            classifications=["TEST_FAILURE"],event_id="success-101",verification_url="https://github.com/example/run/101")
        self.assertEqual(result["resolved"],0); self.assertEqual(doc["incidents"][0]["lifecycle_status"],"MANUAL_INTERVENTION")
    def test_imported_open_incident_archive_is_complete_and_unique(self):
        active = __import__("json").loads((ROOT / "storage" / "v2" / "incidents.json").read_text(encoding="utf-8"))
        archive = __import__("json").loads((ROOT / "storage" / "v2" / "legacy_issue_archive.json").read_text(encoding="utf-8"))
        self.assertEqual(archive["record_count"], 85)
        self.assertEqual(len(archive["records"]), archive["record_count"])
        archive_ids = [item["source_issue_number"] for item in archive["records"]]
        self.assertEqual(len(archive_ids), len(set(archive_ids)))
        archived_legacy_ids = {item["legacy_id"] for item in archive["records"]}
        active_legacy_ids = {item.get("legacy_id") for item in active["incidents"]}
        self.assertTrue(archived_legacy_ids.issubset(active_legacy_ids))
        self.assertGreaterEqual(len(active["incidents"]), archive["record_count"])
        self.assertEqual(active["migration"]["records_imported"], archive["record_count"])

    def test_rejects_partial_source_sha(self):
        with self.assertRaisesRegex(ValueError,"full Git commit SHA"):
            record_incident(seed(),workflow="config_validator",run_id="100",source_sha="deadbeef",
                classification="TEST_FAILURE",event_id="failure-100",summary="test failed",run_url="https://github.com/example/run/100")

if __name__ == "__main__": unittest.main(verbosity=2)
