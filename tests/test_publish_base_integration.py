import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify_publish_base.sh"


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


class PublishBaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        git(self.root, "clone", str(self.remote), str(self.work))
        git(self.work, "config", "user.name", "Test")
        git(self.work, "config", "user.email", "test@example.invalid")
        (self.work / "docs").mkdir()
        (self.work / "shadowrocket").mkdir()
        (self.work / "docs" / "guide.md").write_text("initial\n", encoding="utf-8")
        (self.work / "shadowrocket" / "ss.conf").write_text("protected\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-m", "initial")
        git(self.work, "push", "-u", "origin", "main")
        self.base = git(self.work, "rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def run_guard(self, audited_sha=None):
        env = os.environ.copy()
        env["GITHUB_SHA"] = audited_sha or self.base
        return subprocess.run(
            ["bash", str(VERIFY_SCRIPT)], cwd=self.work, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

    def add_remote_commit(self, path, content, message):
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        git(self.work, "add", path)
        git(self.work, "commit", "-m", message)
        git(self.work, "push", "origin", "HEAD:main")
        git(self.work, "checkout", "--detach", self.base)

    def test_docs_only_change_rebases_to_current_main(self):
        self.add_remote_commit("docs/guide.md", "updated docs\n", "docs update")
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.work, "rev-parse", "origin/main"))
        self.assertEqual((self.work / "docs" / "guide.md").read_text(encoding="utf-8"), "updated docs\n")
        self.assertEqual((self.work / "shadowrocket" / "ss.conf").read_text(encoding="utf-8"), "protected\n")

    def test_non_documentation_change_is_rejected_without_rebase(self):
        self.add_remote_commit("scripts/build_config.py", "changed\n", "script update")
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Non-documentation", result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), self.base)

    def test_divergent_history_is_rejected(self):
        (self.work / "local-only.txt").write_text("local\n", encoding="utf-8")
        git(self.work, "add", "local-only.txt")
        git(self.work, "commit", "-m", "local divergent commit")
        local_commit = git(self.work, "rev-parse", "HEAD")
        git(self.work, "checkout", "--detach", self.base)
        self.add_remote_commit("docs/guide.md", "remote docs\n", "remote docs update")
        git(self.work, "checkout", "--detach", local_commit)
        result = self.run_guard(audited_sha=local_commit)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("not an ancestor", result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), local_commit)


if __name__ == "__main__":
    unittest.main()
