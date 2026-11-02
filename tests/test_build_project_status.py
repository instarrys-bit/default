import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_project_status import build_status, git_blob_sha


class ProjectStatusTests(unittest.TestCase):
    def test_consolidated_report_checks_config_rules_sources_queue_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("rulesets", "sources", "data", "reports/lifecycle", "shadowrocket"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            (root / "rulesets/direct.list").write_text("DOMAIN,direct.example\n", encoding="utf-8")
            (root / "rulesets/proxy.list").write_text("DOMAIN-SUFFIX,proxy.example\n", encoding="utf-8")
            (root / "rulesets/reject.list").write_text("DOMAIN,blocked.example\n", encoding="utf-8")
            (root / "shadowrocket/ss.conf").write_text("[General]\n", encoding="utf-8")
            config_sha = git_blob_sha((root / "shadowrocket/ss.conf").read_bytes())

            def save(path, value):
                (root / path).write_text(json.dumps(value), encoding="utf-8")

            save("rulesets/manifest.json", {
                "rule_count": {"DIRECT": 1, "PROXY": 1, "REJECT": 1},
                "published_rule_total": 3, "approved_total": 3, "held_total": 2,
                "status_count": {"APPROVED": 3, "REVIEW": 2},
                "minimum_independent_sources": 2
            })
            save("rulesets/lifecycle_state.json", {
                "max_published_rules": 30000, "published_rule_count": 3,
                "published_high_water_mark": 3, "next_milestone": 5000,
                "due_milestones": [], "monthly_review_due": False, "queue_mode": False
            })
            save("rulesets/pending_queue.json", {"items": []})
            save("sources/domain_sources.json", {"sources": [
                {"id": "d1", "classification": "DIRECT", "independence_group": "d1"},
                {"id": "d2", "classification": "DIRECT", "independence_group": "d2"},
                {"id": "p1", "classification": "PROXY", "independence_group": "p1"},
                {"id": "p2", "classification": "PROXY", "independence_group": "p2"},
                {"id": "r1", "classification": "REJECT", "independence_group": "r1"},
                {"id": "r2", "classification": "REJECT", "independence_group": "r2"}
            ]})
            save("sources/policy.json", {"managed_config_guard": {
                "path": "shadowrocket/ss.conf", "approved_git_blob_sha": config_sha
            }})
            save("data/candidates.json", {
                "candidate_count": 5, "candidates": [{}, {}, {}, {}, {}],
                "sources": {"d1": {"status": "CURRENT"}, "p1": {"status": "CURRENT"}}
            })
            save("sources/source_activation_log.json", {
                "activations": [{"id": "new-source"}],
                "last_decisions": [{"decision": "activated"}]
            })
            save("sources/discovered_sources.json", {"candidate_count": 10, "candidates": []})
            save("sources/source_assessments.json", {"assessments": [{}, {}, {}]})
            save("sources/source_candidates.json", {"candidates": [{}, {}]})
            save("reports/source-lineage-audit.json", {
                "audited_source_count": 6, "lineage_partial_count": 1,
                "lineage_unverified_count": 5, "lineage_verified_count": 0
            })
            save("rulesets/config_conflict_archive.json", {"items": [
                {"id": "cfg1", "restored_at": None, "superseded_at": None},
                {"id": "cfg2", "restored_at": "2026-11-01T00:00:00Z"}
            ]})
            save("reports/ruleset-config-conflict-sync.json", {"restoration_option_count": 1})
            save("rulesets/deletion_archive.json", {"items": [
                {"id": "del1", "restored_at": None}
            ]})
            save("reports/lifecycle/latest.json", {"status": "not_due"})

            status = build_status(root, now="2026-11-02T00:00:00+00:00")
            self.assertEqual(status["health"], "PASS")
            self.assertEqual(status["rulesets"]["published_total"], 3)
            self.assertEqual(status["rulesets"]["headroom"], 29997)
            self.assertEqual(status["sources"]["enabled_count"], 6)
            self.assertEqual(status["sources"]["degraded_count"], 0)
            self.assertEqual(status["recovery"]["config_conflict_restorable_count"], 1)
            self.assertEqual(status["recovery"]["lifecycle_deletion_restorable_count"], 1)
            self.assertTrue(status["integrity"]["config_baseline_match"])
            self.assertTrue((root / "reports/project-status.md").exists())
            self.assertTrue((root / "reports/project-status.json").exists())


if __name__ == "__main__":
    unittest.main()
