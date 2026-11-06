#!/usr/bin/env bash
set -euo pipefail
bash scripts/verify_publish_base.sh

printf '%s' "$GH_TOKEN" | python3 scripts/resource_lease_runtime.py --repository "$GITHUB_REPOSITORY" --branch main --token-stdin assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE" --proof-json "$RESOURCE_LEASE_PROOF"
archive="$RUNNER_TEMP/audit-artifact/audit-output.tar.gz"
test -s "$archive"
python3 scripts/restore_automation_state.py --publish-outputs --archive "$archive" --root .

git diff --quiet "$GITHUB_SHA" -- modules/uu.conf || {
  echo "Protected config modules/uu.conf changed during audit packaging; refusing to publish."
  exit 1
}

publish_paths=(
  sources/policy.json
  automation/release_manifest.json
  automation/production_workflow_map.json
  automation/resource_write_sets.json
  sources/domain_sources.json
  sources/source_activation_log.json
  reports/lifecycle
  reports/project-status.md
  reports/project-status.json
  reports/automation/heartbeat.json
  reports/automation/state_store.json
  reports/external-domain-audit.md
  reports/config-drift-audit.md
  reports/config-drift-audit.json
  reports/ruleset-reference-audit.md
  reports/ruleset-reference-audit.json
  reports/ruleset-config-overlap-audit.md
  reports/ruleset-config-overlap-audit.json
  reports/ruleset-config-conflict-sync.md
  reports/ruleset-config-conflict-sync.json
  reports/source-lineage-audit.json
  reports/source-discovery.md
  reports/source-assessment.md
  reports/source-candidate-matrix.md
  reports/source-activation.md
  reports/policy-source-overlap.md
  sources/policy_source_overlap.json
  sources/discovered_sources.json
  sources/source_assessments.json
  sources/source_candidates.json
  rulesets/
)
for path in "${publish_paths[@]}"; do
  if [[ -e "$path" ]]; then
    git add -- "$path"
  else
    echo "Optional publish path absent; skipping: $path"
  fi
done

shopt -s nullglob
for pattern in \
  "sources/discovered_sources.json.manifest.json" "sources/discovered_sources.json.parts-"* \
  "sources/source_assessments.json.manifest.json" "sources/source_assessments.json.parts-"* \
  "sources/source_candidates.json.manifest.json" "sources/source_candidates.json.parts-"*; do
  if [[ -e "$pattern" ]]; then git add -- "$pattern"; fi
done

for base in sources/discovered_sources.json sources/source_assessments.json sources/source_candidates.json; do
  if [[ ! -e "$base" ]] && git ls-files --error-unmatch "$base" >/dev/null 2>&1; then
    git add -u -- "$base"
  fi
done

git diff --cached --quiet "$GITHUB_SHA" -- modules/uu.conf || {
  echo "Protected config modules/uu.conf is staged; refusing to commit."
  exit 1
}

printf '%s' "$GH_TOKEN" | python3 scripts/resource_lease_runtime.py --repository "$GITHUB_REPOSITORY" --branch main --token-stdin assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE" --proof-json "$RESOURCE_LEASE_PROOF"

if git diff --cached --quiet; then
  echo "No audit output changes."
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "Run deterministic Shadowrocket domain audit"
printf '%s' "$GH_TOKEN" | python3 scripts/resource_lease_runtime.py --repository "$GITHUB_REPOSITORY" --branch main --token-stdin assert-workflow --task-id "$AUTOMATION_TASK_ID_BASE" --proof-json "$RESOURCE_LEASE_PROOF"
git push origin HEAD:main
