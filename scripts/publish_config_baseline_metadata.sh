#!/usr/bin/env bash
set -euo pipefail

expected="sources/policy.json automation/release_manifest.json automation/production_workflow_map.json automation/resource_write_sets.json reports/config-drift-audit.json"
if [[ "${BASELINE_METADATA_ALLOWLIST:-}" != "$expected" ]]; then
  echo "Baseline metadata allowlist mismatch; refusing to publish." >&2
  exit 1
fi

allowlist=(
  sources/policy.json
  automation/release_manifest.json
  automation/production_workflow_map.json
  automation/resource_write_sets.json
  reports/config-drift-audit.json
)

config_before="$(git rev-parse HEAD:modules/uu.conf)"
git fetch origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "main advanced during metadata preparation; aborting without overwriting newer state."
  exit 75
fi
config_worktree="$(git hash-object modules/uu.conf)"
if [[ "$config_before" != "$config_worktree" ]]; then
  echo "modules/uu.conf changed in the working tree; refusing metadata commit." >&2
  exit 1
fi

unexpected_worktree="$(git diff --name-only | grep -vxFf <(printf '%s\n' "${allowlist[@]}") || true)"
if [[ -n "$unexpected_worktree" ]]; then
  echo "Unexpected modified paths: $unexpected_worktree" >&2
  exit 1
fi

git add -- "${allowlist[@]}"
if git diff --cached --quiet; then
  echo "No baseline metadata changes to publish."
  exit 0
fi

unexpected_staged="$(git diff --cached --name-only | grep -vxFf <(printf '%s\n' "${allowlist[@]}") || true)"
if [[ -n "$unexpected_staged" ]]; then
  echo "Unexpected staged paths: $unexpected_staged" >&2
  exit 1
fi
if git diff --cached --name-only | grep -Fxq "modules/uu.conf"; then
  echo "Protected modules/uu.conf is staged; refusing to commit." >&2
  exit 1
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "Register verified uu.conf baseline metadata"

git fetch origin main
if [[ "$(git rev-parse HEAD^)" != "$(git rev-parse origin/main)" ]]; then
  echo "main advanced before publication; refusing non-fast-forward metadata write."
  exit 75
fi
if [[ "$(git rev-parse HEAD:modules/uu.conf)" != "$(git rev-parse origin/main:modules/uu.conf)" ]]; then
  echo "modules/uu.conf changed on main during metadata transaction; refusing publication." >&2
  exit 1
fi

git push origin HEAD:main
echo "Registered baseline metadata; modules/uu.conf remained byte-for-byte unchanged."
