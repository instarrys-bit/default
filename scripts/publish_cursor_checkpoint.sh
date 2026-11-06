#!/usr/bin/env bash
set -euo pipefail
if git diff --quiet -- sources/review_cursor.json; then
  echo "No checkpoint change to publish."
  exit 0
fi
changed="$(git status --short)"
if [ "$(git diff --name-only)" != "sources/review_cursor.json" ]; then
  echo "Unexpected unstaged path in cursor recovery: $changed"
  exit 1
fi
printf '%s' "$GH_TOKEN" | python3 scripts/resource_lease_runtime.py --repository "$GITHUB_REPOSITORY" --branch main --token-stdin assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE" --proof-json "$RESOURCE_LEASE_PROOF"
git add -- sources/review_cursor.json
if [ "$(git diff --cached --name-only)" != "sources/review_cursor.json" ]; then
  echo "Cursor recovery staged an unexpected path."
  exit 1
fi
git diff --cached --check
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "Persist failed deterministic review cursor"
git fetch origin main
git rebase origin/main
printf '%s' "$GH_TOKEN" | python3 scripts/resource_lease_runtime.py --repository "$GITHUB_REPOSITORY" --branch main --token-stdin assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE" --proof-json "$RESOURCE_LEASE_PROOF"
git push origin HEAD:main
