import json
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
        (self.work / "automation").mkdir()
        (self.work / "automation" / "task_queue.json").write_text(json.dumps({"revision": 0}) + chr(10), encoding="utf-8")
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

    def add_queue_commit(self, *, author_email="41898282+github-actions[bot]@users.noreply.github.com",
                         message="Update durable automation task queue", extra_path=None):
        queue_path = self.work / "automation" / "task_queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps({"revision": 1}) + chr(10), encoding="utf-8")
        git(self.work, "add", "automation/task_queue.json")
        if extra_path:
            extra = self.work / extra_path
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("other change" + chr(10), encoding="utf-8")
            git(self.work, "add", extra_path)
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "github-actions[bot]"
        env["GIT_AUTHOR_EMAIL"] = author_email
        subprocess.run(["git", "commit", "-m", message], cwd=self.work, env=env,
                       check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git(self.work, "push", "origin", "HEAD:main")
        git(self.work, "checkout", "--detach", self.base)

    def run_check_only(self, compare):
        env = os.environ.copy()
        env["GITHUB_SHA"] = self.base
        env["COMPARE_JSON"] = json.dumps(compare)
        return subprocess.run(
            ["bash", str(VERIFY_SCRIPT), "--check-only"], cwd=self.work, env=env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

    def queue_compare(self, *, author_email="41898282+github-actions[bot]@users.noreply.github.com",
                      message="Update durable automation task queue", files=None, parent=None):
        return {
            "status": "ahead",
            "ahead_by": 1,
            "behind_by": 0,
            "files": files or [{"filename": "automation/task_queue.json", "status": "modified"}],
            "commits": [{
                "sha": "a" * 40,
                "commit": {"message": message, "author": {"email": author_email}},
                "parents": [{"sha": parent or self.base}],
            }],
        }

    def test_docs_only_change_rebases_to_current_main(self):
        self.add_remote_commit("docs/guide.md", "updated docs\n", "docs update")
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.work, "rev-parse", "origin/main"))
        self.assertEqual((self.work / "docs" / "guide.md").read_text(encoding="utf-8"), "updated docs\n")
        self.assertEqual((self.work / "shadowrocket" / "ss.conf").read_text(encoding="utf-8"), "protected\n")

    def test_verified_queue_only_commit_rebases_to_current_main(self):
        self.add_queue_commit()
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("strictly verified durable queue-state commits", result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.work, "rev-parse", "origin/main"))
        self.assertEqual((self.work / "shadowrocket" / "ss.conf").read_text(encoding="utf-8").strip(), "protected")

    def test_queue_only_commit_from_non_bot_author_is_rejected(self):
        self.add_queue_commit(author_email="test@example.invalid")
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("untrusted, mixed, or non-linear", result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), self.base)

    def test_queue_commit_mixed_with_other_files_is_rejected(self):
        self.add_queue_commit(extra_path="scripts/changed.py")
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Non-documentation", result.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), self.base)

    def test_api_check_accepts_strict_queue_only_compare(self):
        result = self.run_check_only(self.queue_compare())
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("strictly verified durable queue-state commits", result.stdout)

    def test_api_check_rejects_untrusted_queue_commit(self):
        result = self.run_check_only(self.queue_compare(author_email="test@example.invalid"))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("unverified repository state", result.stdout)

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

    def test_generated_outputs_do_not_create_new_production_demand(self):
        compare = {
            "status": "ahead",
            "files": [
                {"filename": "reports/automation/heartbeat.json", "status": "modified"},
                {"filename": "rulesets/direct.list", "status": "modified"},
                {"filename": "sources/source_activation_log.json", "status": "modified"},
            ],
        }
        result = self.run_check_only(compare)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("No declared production inputs changed", result.stdout)

    def test_declared_production_input_change_requires_new_audit(self):
        compare = {
            "status": "ahead",
            "files": [
                {"filename": "scripts/build_rulesets.py", "status": "modified"},
                {"filename": "reports/automation/heartbeat.json", "status": "modified"},
            ],
        }
        result = self.run_check_only(compare)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("A declared production input changed", result.stdout)

    def test_ss_conf_is_a_read_only_production_input(self):
        compare = {"status": "ahead", "files": [{"filename": "shadowrocket/ss.conf", "status": "modified"}]}
        result = self.run_check_only(compare)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("A declared production input changed", result.stdout)


if __name__ == "__main__":
    unittest.main()
