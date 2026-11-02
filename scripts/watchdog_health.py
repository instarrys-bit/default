#!/usr/bin/env python3
"""Fail-closed interpretation of the published automation health report."""
from __future__ import annotations
import json
import sys
from pathlib import Path

def evaluate_report(path: Path) -> dict:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"health":"UNKNOWN","issue_required":True,"reason":"project health report is missing","search_errors":0,"tree_errors":0,"coverage_stalled":None}
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:
        return {"health":"UNKNOWN","issue_required":True,"reason":"project health report cannot be read: "+str(exc)[:240],"search_errors":0,"tree_errors":0,"coverage_stalled":None}
    if not isinstance(data,dict) or data.get("health") not in {"PASS","CHECK","FAIL"}:
        return {"health":"UNKNOWN","issue_required":True,"reason":"project health report has no valid PASS/CHECK/FAIL health field","search_errors":0,"tree_errors":0,"coverage_stalled":None}
    discovery=data.get("source_discovery") if isinstance(data.get("source_discovery"),dict) else {}
    coverage=data.get("coverage") if isinstance(data.get("coverage"),dict) else {}
    health=data["health"]
    return {
        "health":health,
        "issue_required":health in {"CHECK","FAIL"},
        "reason":"published project health status",
        "search_errors":int(discovery.get("search_error_count",0) or 0),
        "tree_errors":int(discovery.get("tree_error_count",0) or 0),
        "coverage_stalled":bool(coverage.get("stalled",False))
    }

def main():
    result=evaluate_report(Path(sys.argv[1] if len(sys.argv)>1 else "reports/project-status.json"))
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
