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
                target_state="VERIFYING",
            )

    def test_legacy_issue_can_be_bootstrapped_only_with_recovery_evidence(self):
        body, state = transition_incident(
            "Legacy issue body",
            workflow="config_validator",
            source_sha=SHA,
            classification="LEGACY_INCIDENT",
            event_id="verified-run-303",
            target_state="RECOVERED",
            verification_url="https://github.com/example/validator-run",
        )
        self.assertEqual(
            state["history"],
            ["DETECTED", "DIAGNOSING", "MANUAL_INTERVENTION", "RECOVERED"],
        )
        self.assertTrue(body.endswith("\n"))

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


if __name__ == "__main__":
    unittest.main()
