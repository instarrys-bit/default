import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from append_step_summary import DEFAULT_MAX_BYTES, TRUNCATION_MARKER, append_summary


class AppendStepSummaryTests(unittest.TestCase):
    def test_large_report_is_truncated_below_github_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "large.md"
            summary = root / "summary.md"
            source.write_text("A" * 1_200_000, encoding="utf-8")
            result = append_summary(source, summary)
            output = summary.read_bytes()
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(output), DEFAULT_MAX_BYTES)
            self.assertIn(b"Summary truncated", output)

    def test_multiple_appends_share_one_global_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "summary.md"
            first = root / "first.md"
            second = root / "second.md"
            first.write_text("one" * 100, encoding="utf-8")
            second.write_text("two" * 1_000_000, encoding="utf-8")
            append_summary(first, summary, max_bytes=1000)
            result = append_summary(second, summary, max_bytes=1000)
            self.assertLessEqual(summary.stat().st_size, 1000)
            self.assertTrue(result["truncated"])

    def test_small_report_is_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "small.md"
            summary = root / "summary.md"
            source.write_text("short report\n", encoding="utf-8")
            result = append_summary(source, summary)
            self.assertFalse(result["truncated"])
            self.assertEqual(summary.read_text(encoding="utf-8"), "short report\n")

    def test_existing_summary_at_limit_does_not_grow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "more.md"
            summary = root / "summary.md"
            source.write_text("additional", encoding="utf-8")
            summary.write_bytes(b"x" * 500)
            result = append_summary(source, summary, max_bytes=500)
            self.assertEqual(summary.stat().st_size, 500)
            self.assertEqual(result["appended_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
