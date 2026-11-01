import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from auto_activate_sources import activate


def base_registry():
    return {
        "sources": [
            {"id": "old-direct", "publisher": "old/direct", "role": "primary_candidate_source", "url": "https://raw.githubusercontent.com/old/direct/main/list", "format": "domain-only", "weight": 0.4, "classification": "DIRECT", "minimum_entries": 1, "independence_group": "old-direct", "lineage_status": "unverified", "upstream_repositories": []},
            {"id": "old-proxy", "publisher": "old/proxy", "role": "primary_candidate_source", "url": "https://raw.githubusercontent.com/old/proxy/main/list", "format": "domain-only", "weight": 0.4, "classification": "PROXY", "minimum_entries": 1, "independence_group": "old-proxy", "lineage_status": "unverified", "upstream_repositories": []},
            {"id": "old-reject", "publisher": "old/reject", "role": "primary_candidate_source", "url": "https://raw.githubusercontent.com/old/reject/main/list", "format": "domain-only", "weight": 0.4, "classification": "REJECT", "minimum_entries": 1, "independence_group": "old-reject", "lineage_status": "unverified", "upstream_repositories": []}
        ],
        "scoring": {
            "minimum_independent_sources": 2,
            "minimum_confidence": 0.8,
            "source_weights": {"old-direct": 0.4, "old-proxy": 0.4, "old-reject": 0.4},
            "required_sources_by_policy": {"DIRECT": [], "PROXY": [], "REJECT": []}
        }
    }


def candidate(repo="new/direct", policy="DIRECT", drift="unchanged", evidence="README_policy_reference", count=150, archived=False):
    return {
        "repository": repo,
        "policy": policy,
        "activation_eligible": True,
        "archived": archived,
        "domain_set_sha256": "a" * 64,
        "lineage_status": "unverified",
        "lineage_warning": "lineage_not_verified",
        "readme_shared_reference_peers": [{"repository": "other/repo"}],
        "files": [{
            "url": f"https://raw.githubusercontent.com/{repo}/main/domains.list",
            "parser": "domain-only",
            "policy_evidence": evidence,
            "domain_count": count,
            "domain_fingerprint_count": count,
            "sha256": "b" * 64,
            "drift": {"status": drift}
        }]
    }


class AutoActivationTests(unittest.TestCase):
    def test_stable_strong_candidate_activates_without_lineage_veto(self):
        registry, activated, decisions = activate(base_registry(), {"candidates": [candidate()]}, "2026-11-01T00:00:00+00:00")
        self.assertEqual(len(activated), 1)
        source = next(x for x in registry["sources"] if x["id"] == activated[0]["id"])
        self.assertEqual(source["lineage_status"], "unverified")
        self.assertTrue(source["bootstrap_enqueue"])
        self.assertEqual(source["role"], "primary_candidate_source")

    def test_first_observation_is_not_activated(self):
        _, activated, _ = activate(base_registry(), {"candidates": [candidate(drift="baseline_initialized")]})
        self.assertEqual(activated, [])

    def test_weak_policy_evidence_is_not_activated(self):
        _, activated, _ = activate(base_registry(), {"candidates": [candidate(evidence="none")]})
        self.assertEqual(activated, [])

    def test_small_candidate_is_not_activated(self):
        _, activated, _ = activate(base_registry(), {"candidates": [candidate(count=99)]})
        self.assertEqual(activated, [])

    def test_archived_publisher_is_not_activated(self):
        _, activated, _ = activate(base_registry(), {"candidates": [candidate(archived=True)]})
        self.assertEqual(activated, [])

    def test_same_publisher_is_not_registered_twice(self):
        registry = base_registry()
        registry["sources"].append({"id":"existing-new","publisher":"new/direct","role":"independent_policy_corroboration","url":"https://raw.githubusercontent.com/new/direct/old/list","format":"domain-only","weight":0.4,"classification":"DIRECT","minimum_entries":1,"independence_group":"new/direct","lineage_status":"unverified","upstream_repositories":[]})
        registry["scoring"]["source_weights"]["existing-new"] = 0.4
        _, activated, _ = activate(registry, {"candidates": [candidate()]})
        self.assertEqual(activated, [])


if __name__ == "__main__":
    unittest.main()
