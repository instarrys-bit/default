#!/usr/bin/env bash
# Verify the audited commit is still publishable against the current main branch.
# Only documentation-only commits may be incorporated while the audit is running.
set -euo pipefail

: "${GITHUB_SHA:?GITHUB_SHA must identify the exact audited commit}"

git fetch origin main
if ! git merge-base --is-ancestor "$GITHUB_SHA" origin/main; then
  echo "The audited commit is not an ancestor of current main; refusing to publish across divergent history." >&2
  exit 1
fi

changed_paths="$(git diff --name-only "$GITHUB_SHA" origin/main)"
if [ -n "$changed_paths" ]; then
  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    case "$changed_path" in
      docs/*)
        ;;
      *)
        echo "Non-documentation input or repository state changed during audit: $changed_path" >&2
        echo "Refusing to publish stale audit output." >&2
        exit 1
        ;;
    esac
  done <<< "$changed_paths"
  echo "Only docs/ files changed during audit; rebasing publication onto current main."
  git reset --hard origin/main
else
  echo "Audited commit is still current; no rebase required."
fi
