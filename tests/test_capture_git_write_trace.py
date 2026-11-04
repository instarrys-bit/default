import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_git_write_trace import collect_changed_paths


class GitWriteTraceTests(unittest.TestCase):
    def test_collects_committed_worktree_staged_and_untracked_paths(self):
        outputs = iter([
            b"sources/a.json\0reports/b.md\\0",
            b"scripts/c.py\\0",
            b"rulesets/direct.list\\0",
            b"reports/new.md\\0",
        ])
        def runner(args, root):
            return next(outputs)
        self.assertEqual(
            collect_changed_paths("a" * 40, root=ROOT, runner=runner),
            ["reports/b.md", "reports/new.md", "rulesets/direct.list",
             "scripts/c.py", "sources/a.json"],
        )

    def test_rejects_invalid_baseline_sha(self):
        with self.assertRaisesRegex(ValueError, "full lowercase Git commit SHA"):
            collect_changed_paths("not-a-sha", root=ROOT, runner=lambda *_: b"")

    def test_rejects_unsafe_paths_from_git(self):
        with self.assertRaisesRegex(ValueError, "unsafe repository path"):
            collect_changed_paths("a" * 40, root=ROOT, runner=lambda *_: b"../outside\\0")


if __name__ == "__main__":
    unittest.main()
