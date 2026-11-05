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

# The production input manifest is the single source of truth for path
# classification. Queue state remains special: it is accepted only through the
# strict bot-authored linear-CAS check below, never through this generic path.
is_non_input_path_set() {
  local paths_json="$1"
  python3 - "$paths_json" <<'PY'
import json
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from production_intent import classify_paths, load_manifest
paths = json.loads(sys.argv[1])
if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
    raise SystemExit(2)
if "automation/task_queue.json" in paths:
    raise SystemExit(1)
classification = classify_paths(paths, load_manifest(Path("automation/production_inputs.json")))
if classification["status"] != "NO_INPUT_CHANGE":
    print(json.dumps(classification, sort_keys=True), file=sys.stderr)
    raise SystemExit(1)
PY
}

is_non_input_only_compare() {
  jq -e '
    .status == "ahead"
    and (.files | type == "array")
    and (.files | length > 0)
  ' <<< "$compare_json" >/dev/null 2>&1 || return 1
  local paths_json
  paths_json="$(jq -c '[.files[].filename]' <<< "$compare_json")"
  is_non_input_path_set "$paths_json"
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

# A production audit may overlap with verified queue bookkeeping and unrelated
# monitoring/dashboard commits. Validate every commit that touched the queue
# through the commit API, then classify the remaining paths normally.
is_verified_mixed_queue_and_non_input_compare() {
  jq -e '
    .status == "ahead"
    and .behind_by == 0
    and (.ahead_by | type == "number")
    and (.ahead_by >= 1 and .ahead_by <= 20)
    and (.commits | length) == .ahead_by
    and ([.files[].filename] | index("automation/task_queue.json") != null)
    and ([.files[].filename | select(. != "automation/task_queue.json")] | length > 0)
  ' <<< "$compare_json" >/dev/null 2>&1 || return 1

  local queue_commit_seen=false commit_sha detail
  while IFS= read -r commit_sha; do
    [ -n "$commit_sha" ] || continue
    detail="$(gh api "repos/$REPO/commits/$commit_sha")" || return 1
    if jq -e '[.files[]?.filename] | index("automation/task_queue.json") != null' \
      <<< "$detail" >/dev/null 2>&1; then
      queue_commit_seen=true
      jq -e '
        .commit.message == "Update durable automation task queue"
        and .commit.author.email == "41898282+github-actions[bot]@users.noreply.github.com"
        and (.parents | length) == 1
        and (.files | length) == 1
        and .files[0].filename == "automation/task_queue.json"
        and .files[0].status == "modified"
      ' <<< "$detail" >/dev/null 2>&1 || return 1
    fi
  done < <(jq -r '.commits[].sha' <<< "$compare_json")

  [ "$queue_commit_seen" = true ] || return 1
  local non_queue_paths
  non_queue_paths="$(jq -c '[.files[].filename | select(. != "automation/task_queue.json")]' <<< "$compare_json")"
  is_non_input_path_set "$non_queue_paths"
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
  if is_verified_mixed_queue_and_non_input_compare; then
    echo "Only strictly verified queue-state commits and manifest-classified non-production paths changed after the audited commit."
    exit 0
  fi
  if is_non_input_only_compare; then
    echo "No declared production inputs changed after the audited commit; generated outputs and unrelated state do not create production demand."
    exit 0
  fi
  echo "A declared production input changed after the audited commit; a new production audit is required." >&2
  exit 1
fi


# Publish-time equivalent of the API check. Inspect actual Git history so
# queue changes are accepted only when each queue-touching commit is a
# single-file, bot-authored durable queue update.
is_verified_mixed_queue_and_non_input_history() {
  local base="$1" head="$2" paths_json="$3"
  local commits commit parent_line author_email subject changed_status
  commits="$(git rev-list --reverse "$base..$head")" || return 1
  [ -n "$commits" ] || return 1
  [ "$(wc -l <<< "$commits" | tr -d ' ')" -le 20 ] || return 1
  local queue_commit_seen=false
  while IFS= read -r commit; do
    [ -n "$commit" ] || continue
    changed_status="$(git diff-tree --no-commit-id --name-status -r -m "$commit" | sort -u)"
    if grep -Fq 
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

  changed_paths_json="$(printf '%s\n' "$changed_paths" | jq -Rsc 'split("\n") | map(select(length > 0))')"
  if grep -Fxq "automation/task_queue.json" <<< "$changed_paths" &&
     is_verified_mixed_queue_and_non_input_history "$GITHUB_SHA" "$(git rev-parse origin/main)" "$changed_paths_json"; then
    echo "Only strictly verified queue-state commits and manifest-classified non-production paths changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi
  if is_non_input_path_set "$changed_paths_json"; then
    echo "Only manifest-classified non-production paths changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi

  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    echo "Production input or unclassified repository path changed during audit: $changed_path" >&2
  done <<< "$changed_paths"
  echo "Refusing to publish stale audit output." >&2
  exit 1
fi

echo "Audited commit is still current; no rebase required."
\tautomation/task_queue.json' <<< "$changed_status"; then
      queue_commit_seen=true
      parent_line="$(git rev-list --parents -n 1 "$commit")"
      [ "$(wc -w <<< "$parent_line" | tr -d ' ')" -eq 2 ] || return 1
      author_email="$(git show -s --format=%ae "$commit")"
      subject="$(git show -s --format=%s "$commit")"
      [ "$author_email" = "41898282+github-actions[bot]@users.noreply.github.com" ] || return 1
      [ "$subject" = "Update durable automation task queue" ] || return 1
      [ "$changed_status" = 
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

  changed_paths_json="$(printf '%s\n' "$changed_paths" | jq -Rsc 'split("\n") | map(select(length > 0))')"
  if is_non_input_path_set "$changed_paths_json"; then
    echo "Only manifest-classified non-production paths changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi

  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    echo "Production input or unclassified repository path changed during audit: $changed_path" >&2
  done <<< "$changed_paths"
  echo "Refusing to publish stale audit output." >&2
  exit 1
fi

echo "Audited commit is still current; no rebase required."
M\tautomation/task_queue.json' ] || return 1
    fi
  done <<< "$commits"
  [ "$queue_commit_seen" = true ] || return 1
  local non_queue_paths
  non_queue_paths="$(jq -c '[.[] | select(. != "automation/task_queue.json")]' <<< "$paths_json")"
  is_non_input_path_set "$non_queue_paths"
}

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

  changed_paths_json="$(printf '%s\n' "$changed_paths" | jq -Rsc 'split("\n") | map(select(length > 0))')"
  if is_non_input_path_set "$changed_paths_json"; then
    echo "Only manifest-classified non-production paths changed during audit; rebasing publication onto current main."
    git reset --hard origin/main
    exit 0
  fi

  while IFS= read -r changed_path; do
    [ -n "$changed_path" ] || continue
    echo "Production input or unclassified repository path changed during audit: $changed_path" >&2
  done <<< "$changed_paths"
  echo "Refusing to publish stale audit output." >&2
  exit 1
fi

echo "Audited commit is still current; no rebase required."
