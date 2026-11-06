#!/usr/bin/env bash
set -euo pipefail
title="Shadowrocket automation incident (run $RUN_ID)"
body="The deterministic pipeline ended with audit=$AUDIT_RESULT and publish=$PUBLISH_RESULT.\n\nRun: $RUN_URL\nCommit: $COMMIT_SHA\n\n<!-- shadowrocket-automation:workflow=auto_sync;run_id=$RUN_ID -->\n\nPlease inspect the run and logs. This issue is maintained automatically."
existing="$(gh issue list --repo "$REPO" --state open --limit 100 --json number,title | jq --arg title "$title" -r '.[] | select(.title == $title) | .number' | head -n 1)"
if [ -n "$existing" ] && [ "$existing" != "null" ]; then
  gh issue comment "$existing" --repo "$REPO" --body "$body"
else
  gh issue create --repo "$REPO" --title "$title" --body "$body"
fi
