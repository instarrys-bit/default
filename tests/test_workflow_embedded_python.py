"""Compile every quoted Python heredoc embedded in GitHub Actions workflows.

This catches syntax/indentation errors that ordinary YAML parsing cannot detect.
"""
from __future__ import annotations

import re
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_HEREDOC = re.compile(r"^ *(?:python|python3)\b.*<<\s*(['\"])PY\1\s*$")


def extract_python_heredocs(source: str):
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if not PYTHON_HEREDOC.match(line):
            continue
        indent = len(line) - len(line.lstrip(" "))
        terminator = " " * indent + "PY"
        end = next((cursor for cursor in range(index + 1, len(lines)) if lines[cursor] == terminator), None)
        if end is None:
            raise ValueError(f"unterminated Python heredoc at line {index + 1}")
        body = textwrap.dedent("\n".join(lines[index + 1:end]))
        if not body.strip():
            raise ValueError(f"empty Python heredoc at line {index + 1}")
        yield index + 1, body


class WorkflowEmbeddedPythonTests(unittest.TestCase):
    def test_all_workflow_python_heredocs_compile(self):
        workflow_paths = sorted(
            path for pattern in ("*.yml", "*.yaml")
            for path in (ROOT / ".github" / "workflows").rglob(pattern)
        )
        self.assertTrue(workflow_paths, "no GitHub Actions workflow files found")
        block_count = 0
        for path in workflow_paths:
            for line_number, source in extract_python_heredocs(path.read_text(encoding="utf-8")):
                block_count += 1
                with self.subTest(workflow=path.relative_to(ROOT).as_posix(), line=line_number):
                    compile(source, f"{path}:{line_number}", "exec")
        self.assertGreater(block_count, 0, "no quoted Python heredocs found in workflows")

    def test_extractor_preserves_nested_python_indentation(self):
        source = (
            "      python3 - <<'PY'\n"
            "      value = 1\n"
            "      if value:\n"
            "          print(value)\n"
            "      PY\n"
        )
        blocks = list(extract_python_heredocs(source))
        self.assertEqual(len(blocks), 1)
        compile(blocks[0][1], "synthetic-workflow", "exec")

    def test_extractor_rejects_unterminated_heredoc(self):
        with self.assertRaisesRegex(ValueError, "unterminated Python heredoc"):
            list(extract_python_heredocs("    python3 - <<'PY'\n    value = 1\n"))


if __name__ == "__main__":
    unittest.main()
