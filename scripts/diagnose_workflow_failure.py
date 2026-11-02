#!/usr/bin/env python3
"""Deterministically classify failed automation logs; never edits project code."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


STALE_AUDIT_PATTERN = re.compile(
    r"Audit commit ([0-9a-f]{7,40}) is stale; current main is "
    r"([0-9a-f]{7,40})\. (?:Refusing to spend resources on stale review inputs|Stopping before source discovery)\.",
    re.IGNORECASE,
)


def diagnose(log_text: str, run_id: str = "") -> dict:
    lines = log_text.splitlines()
    failed_steps = []
    current_step = None
    for line in lines:
        match = re.search(r"##\[group\]Run (.+)$", line)
        if match:
            current_step = match.group(1).strip()
        if "##[error]Process completed with exit code" in line:
            failed_steps.append(current_step or "unknown step")

    repair_id = None
    evidence = []
    stale_match = STALE_AUDIT_PATTERN.search(log_text)
    baseline_match = re.search(
        r"(?:User config baseline mismatch for shadowrocket/ss\.conf:\s*[0-9a-f]{40};\s*expected\s*[0-9a-f]{40}|ss\.conf differs from the approved baseline)",
        log_text,
        re.IGNORECASE,
    )
    if (
        "test_stale_audit_guard_runs_before_expensive_domain_review" in log_text
        and "cancel-in-progress: true" in log_text
        and "cancel-in-progress: false" in log_text
    ):
        code = "WORKFLOW_TEST_CONTRACT_MISMATCH"
        summary = (
            "The static test expects cancellation of the active audit, while the workflow "
            "intentionally preserves it and relies on stale-commit guards."
        )
        repair_id = "fix_stale_audit_concurrency_contract"
        evidence = [
            line.strip() for line in lines
            if "test_stale_audit_guard_runs_before_expensive_domain_review" in line
            or "cancel-in-progress:" in line
        ][:10]
    elif stale_match:
        code = "STALE_SUPERSEDED"
        summary = (
            "This audit was safely superseded by a newer main commit. "
            "No code repair or incident is needed."
        )
        evidence = [stale_match.group(0)]
    elif baseline_match:
        code = "CONFIG_BASELINE_MISMATCH"
        summary = (
            "The current ss.conf blob differs from its registered baseline. "
            "The config remains read-only; only verified repository-owner config history may be registered."
        )
        evidence = [line.strip() for line in lines if "ss.conf" in line.lower() and "baseline" in line.lower()][:5]
    elif re.search(r"differs from manifest .* count None", log_text, re.IGNORECASE):
        code = "RULESET_MANIFEST_COUNT_MISSING"
        summary = "The final RULE-SET audit could not read a policy count from the manifest."
        repair_id = "refresh_ruleset_manifest"
        evidence = [line.strip() for line in lines if "differs from manifest" in line][:10]
    elif re.search(r"differs from manifest", log_text, re.IGNORECASE):
        code = "RULESET_MANIFEST_COUNT_MISMATCH"
        summary = "The manifest counts do not match the final generated RULE-SET files."
        repair_id = "refresh_ruleset_manifest"
        evidence = [line.strip() for line in lines if "differs from manifest" in line][:10]
    elif re.search(r"timed out|TimeoutError|job exceeded maximum execution time", log_text, re.IGNORECASE):
        code = "WORKFLOW_TIMEOUT"
        summary = "The workflow exceeded a time limit or encountered a timeout."
    elif re.search(r"ModuleNotFoundError|ImportError", log_text):
        code = "PYTHON_IMPORT_FAILURE"
        summary = "A Python module could not be imported."
    elif re.search(r"FAILED \(failures=|FAILED \(errors=|AssertionError", log_text):
        code = "TEST_FAILURE"
        summary = "A deterministic test failed."
    elif "##[error]Process completed with exit code" in log_text and failed_steps:
        code = "UNCLASSIFIED_STEP_FAILURE"
        summary = "A workflow step failed without a recognized safe repair signature."
    else:
        code = "INSUFFICIENT_FAILURE_EVIDENCE"
        summary = "The supplied log did not contain a verifiable failed step; no incident should be opened."

    return {
        "schema_version": 1,
        "run_id": str(run_id),
        "diagnosed_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": code,
        "summary": summary,
        "failed_steps": list(dict.fromkeys(failed_steps)),
        "repair_id": repair_id,
        "automatic_code_change_allowed": repair_id is not None,
        "evidence": evidence,
        "policy": "Only explicitly allowlisted deterministic repairs may be proposed; stale or insufficient logs are not incidents; unknown failures are reported, never patched speculatively.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = diagnose(Path(args.log).read_text(encoding="utf-8", errors="replace"), args.run_id)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
