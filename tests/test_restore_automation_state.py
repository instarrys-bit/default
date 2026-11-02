import io, sys, tarfile, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from restore_automation_state import restore_state

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

if __name__ == "__main__":
    unittest.main()
