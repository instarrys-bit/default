import io, sys, tarfile, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from restore_automation_state import PUBLISH_FILES, restore_state, restore_publish_outputs

class RestoreAutomationStateTests(unittest.TestCase):
    def make_archive(self, path, entries):
        with tarfile.open(path, "w:gz") as tar:
            for name, content in entries:
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name); info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

    def test_restores_required_state_and_ignores_non_state_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"state.tar.gz"
            self.make_archive(archive, [
                ("data/candidates.json", '{"candidates": []}'),
                ("sources/domain_reviews.json", '{"reviews": []}'),
                ("sources/rule_provenance.json", '{"items": []}'),
                ("rulesets/direct.list", "DOMAIN,example.com\n"),
                ("data/source_snapshots/source.txt", "example.com\n"),
            ])
            result=restore_state(archive, root/"repo")
            self.assertEqual(result["restored_files"], 4)
            self.assertTrue((root/"repo/data/candidates.json").exists())
            self.assertTrue((root/"repo/sources/domain_reviews.json").exists())
            self.assertFalse((root/"repo/rulesets/direct.list").exists())
            self.assertTrue((root/"repo/data/source_snapshots/source.txt").exists())

    def test_rejects_incomplete_state_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"state.tar.gz"
            self.make_archive(archive, [("data/candidates.json", "{}")])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                restore_state(archive, root/"repo")


    def test_restores_sharded_review_ledger_and_manifest_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "state.tar.gz"
            entries = [
                ("data/candidates.json.manifest.json", '{"schema_version":1}'),
                ("sources/domain_reviews.json.manifest.json", '{"schema_version":1}'),
                ("sources/domain_reviews.json.parts-abcd/part-000000.jsonl", '{"domain":"example.com"}\\n'),
            ]
            self.make_archive(archive, entries)
            result = restore_state(archive, root / "repo")
            self.assertEqual(result["restored_files"], 3)
            self.assertTrue((root / "repo/sources/domain_reviews.json.manifest.json").exists())
            self.assertTrue((root / "repo/sources/domain_reviews.json.parts-abcd/part-000000.jsonl").exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"state.tar.gz"
            self.make_archive(archive, [
                ("data/candidates.json", "{}"),
                ("sources/domain_reviews.json", "{}"),
                ("data/source_snapshots/../../escape.txt", "bad"),
            ])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                restore_state(archive, root/"repo")


    def test_skips_only_legacy_gnu_tar_self_hardlink_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "state.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in ("data/candidates.json", "sources/domain_reviews.json"):
                    data = b"{}"
                    info = tarfile.TarInfo(name); info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
                duplicate = tarfile.TarInfo("data/candidates.json")
                duplicate.type = tarfile.LNKTYPE
                duplicate.linkname = "data/candidates.json"
                tar.addfile(duplicate)
            result = restore_state(archive, root / "repo")
            self.assertEqual(result["restored_files"], 2)

    def test_rejects_hardlink_to_different_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "state.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in ("data/candidates.json", "sources/domain_reviews.json"):
                    data = b"{}"
                    info = tarfile.TarInfo(name); info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
                link = tarfile.TarInfo("data/domain_candidates.json")
                link.type = tarfile.LNKTYPE
                link.linkname = "data/candidates.json"
                tar.addfile(link)
            with self.assertRaisesRegex(ValueError, "unsupported"):
                restore_state(archive, root / "repo")

    def test_rejects_duplicate_regular_archive_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "state.tar.gz"
            self.make_archive(archive, [
                ("data/candidates.json", "{}"),
                ("sources/domain_reviews.json", "{}"),
                ("data/candidates.json", "{\"duplicate\":true}"),
            ])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                restore_state(archive, root / "repo")


    def test_publish_restore_copies_only_allowlisted_outputs_and_rejects_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"audit.tar.gz"; repo=root/"repo"
            self.make_archive(archive, [
                ("reports/project-status.md", "ok"),
                ("rulesets/direct.list", "DOMAIN,example.com\\n"),
                ("sources/domain_reviews.json", "{\"reviews\":[]}"),
                ("modules/uu.conf", "must-not-copy"),
            ])
            with self.assertRaisesRegex(ValueError, "owner-managed read-only config"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((repo/"modules/uu.conf").exists())
            self.assertFalse((repo/"sources/policy.json").exists())

    def test_publish_restore_copies_reports_rulesets_and_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"audit.tar.gz"; repo=root/"repo"
            self.make_archive(archive, [
                ("sources/policy.json", "{}"),
                ("reports/project-status.md", "ok"),
                ("rulesets/direct.list", "DOMAIN,example.com\\n"),
                ("sources/source_assessments.json.manifest.json", "{}"),
                ("sources/source_assessments.json.parts-abcd/part-000000.jsonl", "{}\\n"),
                ("sources/domain_reviews.json", "ignored"),
            ])
            result=restore_publish_outputs(archive, repo)
            self.assertEqual(result["restored_files"], 4)
            self.assertFalse((repo/"sources/policy.json").exists())
            self.assertTrue((repo/"rulesets/direct.list").exists())
            self.assertTrue((repo/"sources/source_assessments.json.parts-abcd/part-000000.jsonl").exists())
            self.assertFalse((repo/"sources/domain_reviews.json").exists())

    def test_publish_restore_removes_legacy_monolith_when_manifest_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"audit.tar.gz"; repo=root/"repo"
            (repo/"sources").mkdir(parents=True)
            (repo/"sources/discovered_sources.json").write_text("legacy", encoding="utf-8")
            self.make_archive(archive, [("sources/discovered_sources.json.manifest.json", "{}")])
            restore_publish_outputs(archive, repo)
            self.assertFalse((repo/"sources/discovered_sources.json").exists())
            self.assertTrue((repo/"sources/discovered_sources.json.manifest.json").exists())



    def test_policy_input_is_not_restored_from_historical_audit_artifact(self):
        self.assertNotIn("sources/policy.json", PUBLISH_FILES)

if __name__ == "__main__":
    unittest.main()
