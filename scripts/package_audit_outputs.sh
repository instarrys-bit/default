#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob
state_files=(
  sources/domain_reviews.json*
  sources/rule_provenance.json*
  sources/discovered_sources.json*
  sources/source_assessments.json*
  sources/source_candidates.json*
  data/domain_candidates.json*
  data/candidates.json*
)
base_files=(
  sources/review_cursor.json
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
  reports/ruleset-config-conflict-sync.md
  reports/ruleset-config-conflict-sync.json
  reports/ruleset-config-overlap-audit.md
  reports/ruleset-config-overlap-audit.json
  reports/source-lineage-audit.json
  reports/source-discovery.md
  reports/source-assessment.md
  reports/source-candidate-matrix.md
  reports/source-activation.md
  reports/reject-secondary-review.md
  reports/policy-source-overlap.md
  sources/policy_source_overlap.json
  data/domain_candidates.json
  data/source_pending.json
  data/primary_snapshot.txt
  data/secondary_snapshot.txt
  data/source_snapshots
  rulesets
)
declare -A archive_seen=()
archive_inputs=()
for path in "${base_files[@]}" "${state_files[@]}"; do
  [[ -e "$path" ]] || continue
  if [[ -L "$path" ]]; then
    echo "Refusing symlink in automation state: $path" >&2
    exit 1
  fi
  if [[ -z "${archive_seen[$path]+present}" ]]; then
    archive_seen["$path"]=1
    archive_inputs+=("$path")
  fi
done
test "${#archive_inputs[@]}" -gt 0
tar -czf "$RUNNER_TEMP/audit-output.tar.gz" -- "${archive_inputs[@]}"
