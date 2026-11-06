#!/usr/bin/env bash
set -euo pipefail
mkdir -p /tmp/prior-audit-state
pointer="reports/automation/state_store.json"
if [ -s "$pointer" ]; then
  run_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("last_state_run_id", ""))' "$pointer")"
  if [ -z "$run_id" ]; then
    echo "State pointer exists but has no run ID; refusing to reset automation state."
    exit 1
  fi
  run_ids="$run_id"
else
  run_ids="$(gh api "repos/$REPO/actions/runs?per_page=100" --jq '.workflow_runs[] | select(.path == ".github/workflows/auto_sync.yml" and .head_branch == "main") | .id')"
fi
restored=0
for run_id in $run_ids; do
  [ "$run_id" = "$CURRENT_RUN_ID" ] && continue
  artifact_id="$(gh api "repos/$REPO/actions/runs/$run_id/artifacts" --jq '[.artifacts[] | select(.name == "deterministic-audit-output" and .expired == false)] | first | .id // empty' 2>/dev/null || true)"
  if [ -z "$artifact_id" ]; then
    if [ -s "$pointer" ]; then
      echo "The state artifact for recorded run $run_id is missing or expired; refusing destructive reinitialization."
      exit 1
    fi
    continue
  fi
  gh run download "$run_id" --name deterministic-audit-output --dir /tmp/prior-audit-state
  archive="/tmp/prior-audit-state/audit-output.tar.gz"
  test -s "$archive"
  python3 scripts/restore_automation_state.py --archive "$archive" --root .
  echo "Restored high-volume state from audit run $run_id (artifact $artifact_id)."
  restored=1
  break
done
if [ "$restored" -eq 0 ]; then
  if [ -s "$pointer" ]; then
    echo "Recorded automation state could not be restored; refusing to continue."
    exit 1
  fi
  echo "No prior state artifact found; using repository bootstrap state."
fi
