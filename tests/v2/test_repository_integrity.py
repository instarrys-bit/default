from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

import snapshot_repository_integrity as integrity


class FakeGitHub:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, params=None):
        self.calls.append((path, params))
        key = (path, bool(params and params.get("recursive")))
        if key in self.responses:
            return self.responses[key]
        if path in self.responses:
            return self.responses[path]
        raise AssertionError(f"unexpected GitHub API request: {path} {params}")


class RepositoryIntegrityTests(unittest.TestCase):
    def test_inventory_excludes_its_own_immutable_objects_and_pointer(self):
        entries = [
            {"path": "modules/uu.conf", "sha": "a" * 40, "size": 100},
            {"path": "rulesets/direct.list", "sha": "b" * 40, "size": 10},
            {"path": "storage/v2/artifacts/sha256/" + "c" * 64, "sha": "d" * 40, "size": 20},
            {"path": integrity.PROJECTION, "sha": "e" * 40, "size": 30},
        ]
        self.assertEqual(
            [item["path"] for item in integrity.source_entries(entries)],
            ["modules/uu.conf", "rulesets/direct.list"],
        )

    def test_main_base_sha_changes_do_not_create_a_self_trigger_loop(self):
        files = [{"path": "rulesets/direct.list", "sha": "a" * 40, "size": 10}]
        first = [{
            "number": 670, "state": "open", "head_sha": "b" * 40,
            "base_ref": "main", "base_sha": "c" * 40, "changed_files": files,
            "reviews": [], "review_comments": [],
        }]
        second = [{
            "number": 670, "state": "open", "head_sha": "b" * 40,
            "base_ref": "main", "base_sha": "d" * 40, "changed_files": files,
            "reviews": [], "review_comments": [],
        }]
        self.assertEqual(integrity.inventory_digest([], first), integrity.inventory_digest([], second))

    def test_pr_head_changed_file_or_review_change_changes_inventory_digest(self):
        base = [{
            "number": 670, "state": "open", "head_sha": "b" * 40,
            "base_ref": "main", "base_sha": "c" * 40,
            "changed_files": [{"path": "rulesets/direct.list", "blob_sha": "d" * 40, "status": "modified"}],
            "reviews": [], "review_comments": [],
        }]
        changed_head = json.loads(json.dumps(base))
        changed_head[0]["head_sha"] = "e" * 40
        changed_file = json.loads(json.dumps(base))
        changed_file[0]["changed_files"][0]["blob_sha"] = "f" * 40
        changed_review = json.loads(json.dumps(base))
        changed_review[0]["reviews"] = [{"id": 1, "state": "APPROVED", "commit_id": "b" * 40}]
        digest = integrity.inventory_digest([], base)
        self.assertNotEqual(digest, integrity.inventory_digest([], changed_head))
        self.assertNotEqual(digest, integrity.inventory_digest([], changed_file))
        self.assertNotEqual(digest, integrity.inventory_digest([], changed_review))

    def test_protected_config_record_contains_git_blob_and_content_sha_without_writing(self):
        class Client:
            def __init__(self):
                self.calls = []
            def blob_bytes(self, blob_sha):
                self.calls.append(blob_sha)
                return b"[General]\n"

        client = Client()
        entries = [{"path": "modules/uu.conf", "sha": "a" * 40, "size": 12}]
        record = integrity.protected_config_record(client, entries)
        self.assertEqual(record["git_blob_sha"], "a" * 40)
        self.assertEqual(record["sha256"], hashlib.sha256(b"[General]\n").hexdigest())
        self.assertEqual(record["access"], "read_only")
        self.assertEqual(client.calls, ["a" * 40])

    def test_truncated_tree_fallback_preserves_nested_paths(self):
        root = "1" * 40
        nested = "2" * 40
        fake = FakeGitHub({
            (f"/git/commits/{'a' * 40}", False): {"tree": {"sha": root}},
            (f"/git/trees/{root}", True): {"truncated": True, "tree": []},
            f"/git/trees/{root}": {"tree": [
                {"type": "tree", "path": "modules", "sha": nested},
                {"type": "blob", "path": "README.md", "sha": "3" * 40, "size": 5},
            ]},
            f"/git/trees/{nested}": {"tree": [
                {"type": "blob", "path": "uu.conf", "sha": "4" * 40, "size": 7},
            ]},
        })
        entries = integrity.GitHub.tree_entries(fake, "a" * 40)
        self.assertEqual(
            [(item["path"], item["sha"]) for item in entries],
            [("README.md", "3" * 40), ("modules/uu.conf", "4" * 40)],
        )

    def test_storage_management_is_the_only_writer_and_modules_are_never_writable(self):
        from runtime import assert_automation_write_allowed
        assert_automation_write_allowed(integrity.PROJECTION, "storage_management")
        assert_automation_write_allowed(
            "storage/v2/artifacts/sha256/" + "a" * 64,
            "storage_management",
        )
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed(integrity.PROJECTION, "watchdog")
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("modules/uu.conf", "storage_management")

    def test_storage_management_schedules_integrity_inventory_without_cancelling_active_writer(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "*/15 * * * *"', workflow)
        self.assertIn("repository-integrity-snapshot:", workflow)
        self.assertIn("snapshot_repository_integrity.py", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("modules/uu.conf", (ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))

    def test_queue_store_explicitly_allowlists_only_the_integrity_projection(self):
        source = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        self.assertIn(integrity.PROJECTION, source)
        self.assertIn('d.setdefault("latest_snapshot", None)', source)


if __name__ == "__main__":
    unittest.main()
