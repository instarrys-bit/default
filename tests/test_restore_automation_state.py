import io, sys, tarfile, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from restore_automation_state import restore_publish_outputs


class RestoreAutomationStateTests(unittest.TestCase):
    def make_archive(self, path, entries):
        with tarfile.open(path, "w:gz") as tar:
            for name, content in entries:
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

    def test_restores_rulesets_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "rulesets.tar.gz"
            repo = root / "repo"
            self.make_archive(archive, [
                ("rulesets/direct.list", "DOMAIN,example.com\\n"),
                ("rulesets/proxy.list", "DOMAIN,foreign.example\\n"),
                ("rulesets/manifest.json", "{}"),
            ])
            result = restore_publish_outputs(archive, repo)
            self.assertEqual(result["restored_files"], 3)
            self.assertTrue((repo / "rulesets/direct.list").exists())
            self.assertTrue((repo / "rulesets/proxy.list").exists())
            self.assertFalse((repo / "sources").exists())
            self.assertFalse((repo / "reports").exists())

    def test_rejects_non_ruleset_member_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "mixed.tar.gz"
            repo = root / "repo"
            self.make_archive(archive, [
                ("rulesets/direct.list", "DOMAIN,example.com\\n"),
                ("sources/policy.json", "{}"),
            ])
            with self.assertRaisesRegex(ValueError, "non-ruleset path"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((repo / "rulesets/direct.list").exists())
            self.assertFalse((repo / "sources/policy.json").exists())

    def test_rejects_owner_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "config.tar.gz"
            repo = root / "repo"
            self.make_archive(archive, [("modules/uu.conf", "must-not-copy")])
            with self.assertRaisesRegex(ValueError, "non-ruleset path"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((repo / "modules/uu.conf").exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "traversal.tar.gz"
            repo = root / "repo"
            self.make_archive(archive, [("rulesets/../../escape.txt", "bad")])
            with self.assertRaisesRegex(ValueError, "unsafe ruleset archive path"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((root / "escape.txt").exists())

    def test_rejects_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "link.tar.gz"
            repo = root / "repo"
            with tarfile.open(archive, "w:gz") as tar:
                link = tarfile.TarInfo("rulesets/alias.list")
                link.type = tarfile.SYMTYPE
                link.linkname = "../outside"
                tar.addfile(link)
            with self.assertRaisesRegex(ValueError, "unsupported ruleset archive entry"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((repo / "rulesets").exists())

    def test_rejects_duplicate_regular_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "duplicate.tar.gz"
            repo = root / "repo"
            self.make_archive(archive, [
                ("rulesets/direct.list", "DOMAIN,a.example\\n"),
                ("rulesets/direct.list", "DOMAIN,b.example\\n"),
            ])
            with self.assertRaisesRegex(ValueError, "duplicate ruleset archive entry"):
                restore_publish_outputs(archive, repo)
            self.assertFalse((repo / "rulesets/direct.list").exists())


if __name__ == "__main__":
    unittest.main()
