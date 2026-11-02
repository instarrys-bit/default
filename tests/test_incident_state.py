import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from incident_state import IncidentStateError, incident_key, transition_incident


SHA = "a" * 40


class IncidentStateTests(unittest.TestCase):
    def test_stable_incident_key_is_scoped_to_workflow_sha_and_classification(self):
        first = incident_key("deterministic_audit", SHA, "TEST_FAILURE")
        self.assertEqual(first, incident_key("deterministic_audit", SHA, "TEST_FAILURE"))
        self.assertNotEqual(first, incident_key("config_validator", SHA, "TEST_FAILURE"))
        self.assertNotEqual(first, incident_key("deterministic_audit", "b" * 40, "TEST_FAILURE"))

    def test_new_incident_records_detection_diagnosis_and_manual_escalation(self):
        body, state = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        self.assertEqual(state["state"], "MANUAL_INTERVENTION")
        self.assertEqual(
            state["history"],
            ["DETECTED", "DIAGNOSING", "MANUAL_INTERVENTION"],
        )
        self.assertIn("shadowrocket-incident-state:v1", body)

    def test_duplicate_event_is_idempotent(self):
        kwargs = dict(
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        body, first = transition_incident("Failure summary", **kwargs)
        repeated_body, repeated = transition_incident(body, **kwargs)
        self.assertEqual(repeated_body, body)
        self.assertEqual(repeated["revision"], first["revision"])

    def test_verified_recovery_is_the_only_path_to_recovered(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="verified-run-202",
                target_state="RECOVERED",
            )
        recovered_body, recovered = transition_incident(
            body,
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="verified-run-202",
            target_state="RECOVERED",
            verification_url="https://github.com/example/recovery-run",
        )
        self.assertEqual(recovered["state"], "RECOVERED")
        self.assertEqual(recovered["revision"], 2)
        self.assertEqual(recovered["verification"]["event_id"], "verified-run-202")
        self.assertIn("RECOVERED", recovered_body)

    def test_invalid_transition_is_rejected(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="verify-run-1",
                target_state="DETECTED",
            )

    def test_legacy_issue_must_persist_verifying_before_recovered(self):
        with self.assertRaises(IncidentStateError):
            transition_incident(
                "Legacy issue body",
                workflow="config_validator",
                source_sha=SHA,
                classification="LEGACY_INCIDENT",
                event_id="verified-run-303",
                target_state="RECOVERED",
                verification_url="https://github.com/example/validator-run",
            )
        body, _ = transition_incident(
            "Legacy issue body",
            workflow="config_validator",
            source_sha=SHA,
            classification="LEGACY_INCIDENT",
            event_id="verifying-run-302",
            target_state="VERIFYING",
        )
        recovered_body, recovered = transition_incident(
            body,
            workflow="config_validator",
            source_sha=SHA,
            classification="LEGACY_INCIDENT",
            event_id="verified-run-303",
            target_state="RECOVERED",
            verification_url="https://github.com/example/validator-run",
        )
        self.assertEqual(
            recovered["history"][-2:],
            ["VERIFYING", "RECOVERED"],
        )
        self.assertTrue(recovered_body.endswith("\n"))

    def test_corrupt_persisted_state_fails_closed(self):
        body = "x\n<!-- shadowrocket-incident-state:v1\nnot-json\n-->\n"
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="event-1",
                target_state="MANUAL_INTERVENTION",
            )

    def test_event_id_cannot_be_reused_for_another_transition(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="failure-run-101",
                target_state="RECOVERED",
                verification_url="https://github.com/example/run",
            )


    def test_verification_phase_must_precede_recovered(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        verifying_body, verifying = transition_incident(
            body,
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="verification-run-202",
            target_state="VERIFYING",
        )
        self.assertEqual(verifying["state"], "VERIFYING")
        _, recovered = transition_incident(
            verifying_body,
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="verified-run-303",
            target_state="RECOVERED",
            verification_url="https://github.com/example/verified-run",
        )
        self.assertEqual(
            recovered["history"][-2:],
            ["VERIFYING", "RECOVERED"],
        )


    def test_persisted_source_sha_mismatch_is_rejected(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha="b" * 40,
                classification="TEST_FAILURE",
                event_id="wrong-sha-202",
                target_state="VERIFYING",
            )

    def test_recovered_cannot_skip_verifying(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="verified-run-202",
                target_state="RECOVERED",
                verification_url="https://github.com/example/verified-run",
            )

    def test_corrupt_history_or_revision_fails_closed(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        state_match = __import__("re").search(
            r"<!-- shadowrocket-incident-state:v1\\n(.*?)\\n-->",
            body,
            __import__("re").DOTALL,
        )
        state = json.loads(state_match.group(1))
        state["history"][-1] = "RECOVERED"
        corrupt = body[:state_match.start(1)] + json.dumps(state) + body[state_match.end(1):]
        with self.assertRaises(IncidentStateError):
            transition_incident(
                corrupt,
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="next-event",
                target_state="VERIFYING",
            )

    def test_multiple_state_blocks_fail_closed(self):
        body, _ = transition_incident(
            "Failure summary",
            workflow="deterministic_audit",
            source_sha=SHA,
            classification="TEST_FAILURE",
            event_id="failure-run-101",
            target_state="MANUAL_INTERVENTION",
        )
        with self.assertRaises(IncidentStateError):
            transition_incident(
                body + "\\n" + body.split("Failure summary", 1)[1],
                workflow="deterministic_audit",
                source_sha=SHA,
                classification="TEST_FAILURE",
                event_id="next-event",
                target_state="VERIFYING",
            )

if __name__ == "__main__":
    unittest.main()
