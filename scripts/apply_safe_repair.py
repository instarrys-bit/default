#!/usr/bin/env python3
"""Apply only reviewed, idempotent repair recipes to an isolated working branch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPAIR_ID = "refresh_ruleset_manifest"
WORKFLOW = Path(".github/workflows/auto_sync.yml")
SCRIPT_PATH = "scripts/refresh_ruleset_manifest.py"
STEP = """      - name: Reconcile final RULE-SET manifest counts
        run: python3 scripts/refresh_ruleset_manifest.py

"""


def apply(root: Path, diagnosis: dict) -> list[str]:
    if diagnosis.get("repair_id") != REPAIR_ID or diagnosis.get("automatic_code_change_allowed") is not True:
        raise ValueError("diagnosis does not authorize a known safe repair")
    root = Path(root)
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
    print(json.dumps({"repair_id": REPAIR_ID, "changed_files": changed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
