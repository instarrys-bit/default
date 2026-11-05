#!/usr/bin/env python3
"""Apply only reviewed, idempotent repair recipes to an isolated working branch."""
from __future__ import annotations


import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPAIR_ID = "refresh_ruleset_manifest"
STALE_TEST_REPAIR_ID = "fix_stale_audit_concurrency_contract"
WORKFLOW = Path(".github/workflows/auto_sync.yml")
STALE_TEST_PATH = Path("tests/test_workflow_config_guard_order.py")
SCRIPT_PATH = "scripts/refresh_ruleset_manifest.py"
STEP = """      - name: Reconcile final RULE-SET manifest counts
        run: python3 scripts/refresh_ruleset_manifest.py

"""
STALE_ASSERTION = '        self.assertIn("cancel-in-progress: true", workflow)'
CURRENT_ASSERTIONS = (
    '        self.assertIn("cancel-in-progress: false", workflow)\n'
    '        self.assertIn("Keep the active audit; stale-commit guards stop obsolete runs safely.", workflow)'
)

def has_safe_main_writer_concurrency(workflow_text: str) -> bool:
    """Read the actual top-level concurrency mapping, ignoring comments and nested jobs."""
    lines = workflow_text.splitlines()
    headers = [index for index, line in enumerate(lines) if line == "concurrency:"]
    if len(headers) != 1:
        return False

    start = headers[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index]
        if line.strip() and not line.startswith((" ", "\t", "#")):
            end = index
            break

    values = {}
    for line in lines[start:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):[ \t]*(.*?)[ \t]*", line)
        if not match:
            continue
        key, value = match.groups()
        if key in values:
            return False
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value

    return (
        values.get("group") == "shadowrocket-main-writer"
        and values.get("cancel-in-progress") == "false"
    )


def apply(root: Path, diagnosis: dict) -> list[str]:
    repair_id = diagnosis.get("repair_id")
    if diagnosis.get("automatic_code_change_allowed") is not True:
        raise ValueError("diagnosis does not authorize a known safe repair")
    root = Path(root)
    workflow_path = root / WORKFLOW
    if not workflow_path.is_file() or not has_safe_main_writer_concurrency(
        workflow_path.read_text(encoding="utf-8")
    ):
        raise ValueError("workflow does not contain the safe top-level main-writer concurrency policy")

    if repair_id == STALE_TEST_REPAIR_ID:
        test_path = root / STALE_TEST_PATH
        if not test_path.is_file():
            raise ValueError("workflow contract test is missing; refusing to synthesize it")
        test_text = test_path.read_text(encoding="utf-8")
        count = test_text.count(STALE_ASSERTION)
        if count == 1:
            test_path.write_text(test_text.replace(STALE_ASSERTION, CURRENT_ASSERTIONS, 1), encoding="utf-8")
            return [str(STALE_TEST_PATH)]
        if count == 0 and CURRENT_ASSERTIONS in test_text:
            return []
        raise ValueError("stale concurrency assertion is missing or ambiguous; refusing a speculative edit")

    if repair_id != REPAIR_ID:
        raise ValueError("diagnosis does not authorize a known safe repair")
    if not (root / SCRIPT_PATH).is_file():
        raise ValueError("allowlisted repair script is missing; refusing to synthesize code")
    workflow_path = root / WORKFLOW
    text = workflow_path.read_text(encoding="utf-8")
    changed = []
    if "python3 scripts/refresh_ruleset_manifest.py" not in text:
        marker = "      - name: Build append-only rule-level provenance ledger\n"
        if text.count(marker) != 1:
            raise ValueError("workflow insertion point is missing or ambiguous")
        text = text.replace(marker, STEP + marker, 1)
        changed.append(str(WORKFLOW))
    compile_line = "python3 -m py_compile "
    lines = text.splitlines()
    compile_indices = [i for i, line in enumerate(lines) if compile_line in line]
    if len(compile_indices) != 1:
        raise ValueError("workflow compile step is missing or ambiguous")
    if SCRIPT_PATH not in lines[compile_indices[0]]:
        lines[compile_indices[0]] = lines[compile_indices[0]].replace(
            "scripts/build_rule_provenance.py",
            "scripts/build_rule_provenance.py " + SCRIPT_PATH,
            1,
        )
        text = "\n".join(lines) + "\n"
        if str(WORKFLOW) not in changed:
            changed.append(str(WORKFLOW))
    if changed:
        workflow_path.write_text(text, encoding="utf-8")
    return changed

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnosis", required=True)
    args = parser.parse_args()
    diagnosis = json.loads(Path(args.diagnosis).read_text(encoding="utf-8"))
    changed = apply(ROOT, diagnosis)
    print(json.dumps({"repair_id": diagnosis.get("repair_id"), "changed_files": changed}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
