import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sync_ruleset_config_conflicts import sync


def config_with_rules(rules):
    return (
        "[General]\nskip-proxy = \n[Rule]\n"
        + "\n".join(rules) + "\n"
        + "RULE-SET,https://example.invalid/reject.list,REJECT\n"
        + "RULE-SET,https://example.invalid/proxy.list,PROXY\n"
        + "RULE-SET,https://example.invalid/direct.list,DIRECT\n"
        + "GEOIP,CN,DIRECT\nFINAL,PROXY\n[Host]\n"
    )


class ConfigConflictRunReportTests(unittest.TestCase):
    def test_repeated_sync_passes_keep_first_pass_deletions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("shadowrocket", "rulesets", "reports"):
                (root / folder).mkdir()
            (root / "shadowrocket" / "ss.conf").write_text(
                config_with_rules(["DOMAIN,api.example.com,PROXY"]), encoding="utf-8"
            )
            (root / "rulesets" / "direct.list").write_text(
                "DOMAIN,api.example.com\nDOMAIN,keep.example.com\n", encoding="utf-8"
            )
            (root / "rulesets" / "proxy.list").write_text("", encoding="utf-8")
            (root / "rulesets" / "reject.list").write_text("", encoding="utf-8")
            (root / "rulesets" / "pending_queue.json").write_text(
                json.dumps({"schema_version": 1, "max_published_rules": 30000, "queued_count": 0, "items": []}),
                encoding="utf-8"
            )
            with patch.dict("os.environ", {"GITHUB_RUN_ID": "test-run-123", "RULESET_CONFIG_REPORT_AGGREGATION": "1"}):
                first = sync(root=root, now="2026-11-02T00:00:00+00:00")
                second = sync(root=root, now="2026-11-02T00:01:00+00:00")
            saved = json.loads((root / "reports" / "ruleset-config-conflict-sync.json").read_text(encoding="utf-8"))
            self.assertEqual(first["published_removed_count"], 1)
            self.assertEqual(second["published_removed_count"], 0)
            self.assertEqual(saved["workflow_run_id"], "test-run-123")
            self.assertEqual(saved["published_removed_count"], 1)
            self.assertEqual(saved["removed_count"], 1)
            self.assertEqual(len(saved["removed"]), 1)
            self.assertEqual(len(saved["sync_passes"]), 2)
            self.assertEqual(saved["published_before"]["DIRECT"], 2)
            self.assertEqual(saved["published_after"]["DIRECT"], 1)
            markdown = (root / "reports" / "ruleset-config-conflict-sync.md").read_text(encoding="utf-8")
            self.assertIn("DOMAIN,api.example.com", markdown)
            self.assertIn("Published rules removed: 1", markdown)


if __name__ == "__main__":
    unittest.main()
