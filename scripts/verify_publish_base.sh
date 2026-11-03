#!/usr/bin/env bash
# Verify the audited commit is still publishable against current main.
# Documentation-only changes and strictly verified bot queue-state commits are safe.
set -euo pipefail

mode="${1:-publish}"
: "${GITHUB_SHA:?GITHUB_SHA must identify the exact audited commit}"

is_docs_only_compare() {
  jq -e '
    .status == "ahead"
    and (.files | length > 0)
    and all(.files[]; (.filename | startswith("docs/")))
  ' >/dev/null 2>&1
}

# Only declared production inputs may create a new production intent.
# Generated rulesets, reports, queue state, and unrelated repository files are outputs/state.
is_production_input_path() {
  case "$1" in
    .github/workflows/*|scripts/*|tests/*|\
    sources/policy.json|sources/domain_sources.json|sources/policy_approvals.json|\
    sources/protected_domains.json|sources/request_domain_observations.json|\
    sources/reject_manual_approvals.json|\
    shadowrocket/ss.conf|automation/program_registry.json|automation/execution_adapters.json)
      return 0 ;;
    *) return 1 ;;
  esac
}

is_non_input_only_compare() {
  jq -e '
    .status == "ahead"
    and (.files | type == "array")
    and (.files | length > 0)
  ' >/dev/null 2>&1 || return 1
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if is_production_input_path "$path"; then
      return 1
    fi
  done < <(jq -r '.files[].filename' <<< "$compare_json")
  return 0
}

is_queue_only_compare() {
  jq -e --arg base "$GITHUB_SHA" '
    .status == "ahead"
    and .behind_by == 0
    and (.ahead_by | type == "number")
    and (.ahead_by >= 1 and .ahead_by <= 20)
    and (.commits | length) == .ahead_by
    and (.files | length) == 1
    and .files[0].filename == "automation/task_queue.json"
    and .files[0].status == "modified"
    and all(.commits[];
      .commit.message == "Update durable automation task queue"
      and .commit.author.email == "41898282+github-actions[bot]@users.noreply.github.com"
      and (.parents | length) == 1
    )
    and .commits[0].parents[0].sha == $base
    and (
      [.commits[].sha] as $shas
      | [.commits[].parents[0].sha] as $parents
      | all(range(1; ($shas | length)); . as $i | $parents[$i] == $shas[$i - 1])
    )
  ' >/dev/null 2>&1
}

if [ "$mode" = "--check-only" ]; then
  if [ -n "${COMPARE_JSON_FILE:-}" ]; then
    compare_json="$(cat "$COMPARE_JSON_FILE")"
  elif [ -n "${COMPARE_JSON:-}" ]; then
    compare_json="$COMPARE_JSON"
  else
    : "${GH_TOKEN:?GH_TOKEN is required for API-only publish-base checks}"
    : "${REPO:?REPO is required for API-only publish-base checks}"
    current_main="$(gh api "repos/$REPO/commits/main" --jq .sha)"
    if [ "$current_main" = "$GITHUB_SHA" ]; then
      echo "Audited commit is still current."
      exit 0
    fi
    compare_json="$(gh api "repos/$REPO/compare/$GITHUB_SHA...$current_main")" || {
      echo "Unable to classify current-main advancement; refusing stale audit work." >&2
      exit 1
    }
  fi

  if is_docs_only_compare <<< "$compare_json"; then
    echo "Only docs/ files changed after the audited commit; review inputs remain current."
    exit 0
  fi
  if is_queue_only_compare <<< "$compare_json"; then
    echo "Only strictly verified durable queue-state commits changed after the audited commit."
    exit 0
  fi
  if is_non_input_only_compare; then
    echo "No declared production inputs changed after the audited commit; generated outputs and unrelated state do not create production demand."
    exit 0
  fi
  echo "A declared production input changed after the audited commit; a new production audit is required." >&2
  exit 1
fi

if [ "$mode" != "publish" ]; then
  echo "Usage: $0 [--check-only]" >&2
  exit 2
fi

git fetch origin main
if ! git merge-base --is-ancestor "$GITHUB_SHA" origin/main; then
  echo "The audited commit is not an ancestor of current main; refusing to publish across divergent history." >&2
  exit 1
fi

changed_paths="$(git diff --name-only "$GITHUB_SHA" origin/main)"
if [ -n "$changed_paths" ]; then
  docs_only=true
  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    case "$changed_path" in
      docs/*)
        ;;
      *)
        docs_only=false
        ;;
    esac
  done <<< "$changed_paths"

  if [ "$docs_only" = true ]; then
    echo "Only docs/ files changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi

  if [ "$changed_paths" = "automation/task_queue.json" ]; then
    mapfile -t queue_commits < <(git rev-list --reverse --first-parent "$GITHUB_SHA..origin/main")
    if [ "${#queue_commits[@]}" -lt 1 ] || [ "${#queue_commits[@]}" -gt 20 ]; then
      echo "Queue-only advancement is outside the bounded commit window; refusing to publish." >&2
      exit 1
    fi

    expected_parent="$GITHUB_SHA"
    expected_status="$(printf 'M\tautomation/task_queue.json')"
    for commit in "${queue_commits[@]}"; do
      read -r commit_sha parent_sha extra <<< "$(git rev-list --parents -n 1 "$commit")"
      author_email="$(git show -s --format=%ae "$commit")"
      subject="$(git show -s --format=%s "$commit")"
      changed_status="$(git diff-tree --no-commit-id --name-status -r "$parent_sha" "$commit")"
      if [ "$commit_sha" != "$commit" ] || [ -n "${extra:-}" ] ||
         [ "$parent_sha" != "$expected_parent" ] ||
         [ "$author_email" != "41898282+github-actions[bot]@users.noreply.github.com" ] ||
         [ "$subject" != "Update durable automation task queue" ] ||
         [ "$changed_status" != "$expected_status" ]; then
        echo "Queue state advanced with an untrusted, mixed, or non-linear commit; refusing to publish stale audit output." >&2
        exit 1
      fi
      expected_parent="$commit"
    done

    if [ "$expected_parent" != "$(git rev-parse origin/main)" ]; then
      echo "Queue-only commit chain does not terminate at current main; refusing to publish." >&2
      exit 1
    fi
    echo "Only strictly verified durable queue-state commits changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi

  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    echo "Non-documentation input or repository state changed during audit: $changed_path" >&2
  done <<< "$changed_paths"
  echo "Refusing to publish stale audit output." >&2
  exit 1
fi

echo "Audited commit is still current; no rebase required."
