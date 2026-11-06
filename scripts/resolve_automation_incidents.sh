#!/usr/bin/env bash
set -euo pipefail
issues="$(gh issue list --repo "$REPO" --state open --search '"Shadowrocket automation" in:title' --json number,title,body | jq --argjson run_id "$RUN_ID" '.[] | select((.title | startswith("Shadowrocket automation failure (run ")) or (.title | startswith("Shadowrocket automation incident (run "))) | select(.body | contains("shadowrocket-automation:workflow=auto_sync;run_id=")) | select(((.body | capture("shadowrocket-automation:workflow=auto_sync;run_id=(?<id>[0-9]+)") | .id | tonumber) < $run_id)) | .number')"
if [ -z "$issues" ]; then
  echo "No earlier, explicitly linked auto_sync incident to resolve."
  exit 0
fi
while IFS= read -r issue; do
  [ -n "$issue" ] || continue
  gh issue comment "$issue" --repo "$REPO" --body "A later full deterministic audit and publish succeeded. Recovery run: $RUN_URL"
  gh issue close "$issue" --repo "$REPO"
done <<< "$issues"
