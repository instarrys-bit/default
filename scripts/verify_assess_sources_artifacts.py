#!/usr/bin/env python3
"""Independently verify assess_sources output artifacts against its stdout result."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from json_document_store import read_document

ROOT=Path(__file__).resolve().parents[1]
ARTIFACT_ROOT=Path(os.environ.get("AUTOMATION_ARTIFACT_ROOT", ROOT)).resolve()
RUNTIME=ARTIFACT_ROOT/"data/source_assessments_runtime.json"
PERSISTENT=ARTIFACT_ROOT/"sources/source_assessments.json"
REPORT=ARTIFACT_ROOT/"reports/source-assessment.md"
PARSER_TYPES={"domain-only","adblock-domain-rules","shadowrocket-domain-rules","quantumult-domain-rules"}


def verify(result_path: Path) -> dict:
    try:
        result=json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read assessor stdout result: {exc}") from exc
    if not isinstance(result,dict):
        raise ValueError("assessor stdout result must be an object")
    for artifact in (RUNTIME, PERSISTENT):
        if not artifact.is_file() and not artifact.with_name(artifact.name + ".manifest.json").is_file():
            raise ValueError(f"required assessment artifact is missing: {artifact.relative_to(ROOT)}")
    runtime=read_document(RUNTIME,"assessments",{"assessments":[]})
    persistent=read_document(PERSISTENT,"assessments",{"assessments":[]})
    assessments=runtime.get("assessments")
    history=persistent.get("assessments")
    if not isinstance(assessments,list) or not isinstance(history,list):
        raise ValueError("assessment artifacts must contain assessments arrays")
    assessed=result.get("assessed")
    if isinstance(assessed,bool) or not isinstance(assessed,int) or assessed<0:
        raise ValueError("stdout assessed count is invalid")
    if len(assessments)!=assessed or runtime.get("assessment_count")!=assessed or runtime.get("assessed_this_run_count")!=assessed:
        raise ValueError("runtime assessment count does not match stdout")
    if runtime.get("activation_count")!=0 or result.get("activated")!=0:
        raise ValueError("assessment capability must never activate a source")
    if runtime.get("total_bytes_read")!=result.get("bytes_read"):
        raise ValueError("runtime byte count does not match stdout")
    parser_count=sum(1 for x in assessments if x.get("parser_candidate") in PARSER_TYPES)
    policy_count=sum(1 for x in assessments if x.get("policy_candidate"))
    if parser_count!=result.get("parser_candidates") or policy_count!=result.get("policy_candidates"):
        raise ValueError("stdout parser/policy counts do not match runtime artifacts")
    if persistent.get("assessment_count")!=len(history):
        raise ValueError("persistent assessment history count is inconsistent")
    historical_count=persistent.get("historical_assessment_count")
    if historical_count is not None and historical_count != len(history):
        raise ValueError("persistent historical assessment count is inconsistent")
    if any(not isinstance(item,dict) for item in history):
        raise ValueError("persistent assessment history contains malformed records")
    if any("domain_fingerprints" in item for item in history if isinstance(item,dict)):
        raise ValueError("persistent assessment history must not contain ephemeral fingerprints")
    if not REPORT.is_file() or REPORT.stat().st_size==0:
        raise ValueError("human-readable assessment report is missing or empty")
    for item in assessments:
        if not isinstance(item,dict) or not isinstance(item.get("url"),str) or not isinstance(item.get("repository"),str):
            raise ValueError("runtime assessment entry is malformed")
    artifact_root = RUNTIME.parents[1]
    return {"valid":True,"assessed":assessed,"historical_assessments":len(history),
            "report_bytes":REPORT.stat().st_size,"activation_count":0,
            "verified_artifacts":[str(RUNTIME.relative_to(artifact_root)),str(PERSISTENT.relative_to(artifact_root)),str(REPORT.relative_to(artifact_root))]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json-file",type=Path,required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(verify(args.result_json_file),sort_keys=True))
        return 0
    except (ValueError,OSError) as exc:
        print(f"ASSESSMENT ARTIFACT VERIFICATION FAILED: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
