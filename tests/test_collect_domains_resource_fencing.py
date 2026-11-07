import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CollectDomainsResourceFenceTests(unittest.TestCase):
    def test_auto_sync_declares_source_snapshot_parent_lease(self):
        adapters = json.loads((ROOT / "automation/execution_adapters.json").read_text(encoding="utf-8"))
        auto_sync = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_auto_sync")
        self.assertIn("data/source_snapshots", auto_sync["resource_contract"]["resource_keys"])

    def test_collect_domains_fences_parent_and_each_dynamic_snapshot_path(self):
        source = (ROOT / "scripts/collect_domains.py").read_text(encoding="utf-8")
        self.assertIn('assert_resource_lease_for_repository_path(ROOT, "data/source_snapshots")', source)
        self.assertIn("assert_resource_lease_for_repository_path(ROOT, path.relative_to(ROOT).as_posix())", source)
        self.assertLess(
            source.index('assert_resource_lease_for_repository_path(ROOT, path.relative_to(ROOT).as_posix())'),
            source.index('path.write_text("\\n".join(sorted(info["domains"]))'),
        )

    def test_source_snapshot_group_is_in_both_resource_inventories(self):
        write_sets = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
        ownership = json.loads((ROOT / "automation/resource_ownership_audit.json").read_text(encoding="utf-8"))
        self.assertTrue(any(item["resource"] == "data/source_snapshots/<source_id>.txt" for item in write_sets["confirmed_shared_write_groups"]))
        self.assertTrue(any(item["id"] == "source_snapshot_files" and "workflow_auto_sync" in item["known_writers"] for item in ownership["resource_groups"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
