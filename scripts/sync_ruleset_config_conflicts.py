#!/usr/bin/env python3
"""Remove only provable conflicts between published/pending rule sets and the user-owned config."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULESETS = ROOT / "rulesets"
CONFIG = ROOT / "shadowrocket" / "ss.conf"
ARCHIVE = RULESETS / "config_conflict_archive.json"
REPORT_JSON = ROOT / "reports" / "ruleset-config-conflict-sync.json"
REPORT_MD = ROOT / "reports" / "ruleset-config-conflict-sync.md"
POLICIES = ("DIRECT", "PROXY", "REJECT")

from audit_ruleset_config_overlap import (
    first_ruleset_line,
    prior_rule_lines,
    parse_skip_proxy,
    match_candidate,
    skip_proxy_match,
)


def parse_rule_line(policy: str, line: str) -> tuple[str, str, str]:
    fields = [part.strip() for part in line.split(",")]
    if len(fields) != 2 or fields[0].upper() not in {"DOMAIN", "DOMAIN-SUFFIX"}:
        raise ValueError("unsupported published rule: " + line)
    kind = fields[0].upper()
    domain = fields[1].lower().rstrip(".")
    if policy.upper() not in POLICIES:
        raise ValueError("invalid policy for published rule: " + policy)
    if not domain:
        raise ValueError("empty domain in published rule: " + line)
    return kind, domain, "suffix_candidate" if kind == "DOMAIN-SUFFIX" else "exact_candidate"


def make_rule(policy: str, scope: str, domain: str) -> str:
    kind = "DOMAIN-SUFFIX" if scope == "suffix_candidate" else "DOMAIN"
    return kind + "," + domain.lower().rstrip(".")


def classify_rule(policy: str, line: str, prior_rules: list[tuple[int, str]], skip_entries: list[str]) -> dict:
    policy = policy.upper()
    kind, domain, scope = parse_rule_line(policy, line)
    match = match_candidate(domain, policy, prior_rules, scope)
    if match["status"] == "CONFLICT":
        return {
            "status": "CONFLICT",
            "domain": domain,
            "scope": scope,
            "effective_policy": match.get("effective_policy"),
            "config_line": match.get("line"),
            "config_rule": match.get("rule"),
            "reason": match.get("reason", "Earlier user-config rule has a different effective policy"),
        }
    bypass = skip_proxy_match(domain, skip_entries, scope)
    if policy != "DIRECT" and bypass:
        return {
            "status": "CONFLICT",
            "domain": domain,
            "scope": scope,
            "effective_policy": "DIRECT",
            "config_line": None,
            "config_rule": "skip-proxy = " + bypass,
            "reason": "User-config skip-proxy bypasses this domain before the proxy/reject rule-set can apply",
        }
    if match["status"] in {"POTENTIAL_MATCH", "CONDITIONAL_POTENTIAL", "UNRESOLVED_RULE"}:
        return {
            "status": "REVIEW",
            "domain": domain,
            "scope": scope,
            "effective_policy": match.get("effective_policy"),
            "config_line": match.get("line"),
            "config_rule": match.get("rule"),
            "reason": match.get("reason", "A possible overlap exists but is not provable"),
        }
    return {
        "status": "NO_CONFLICT",
        "domain": domain,
        "scope": scope,
        "effective_policy": match.get("effective_policy"),
        "config_line": match.get("line"),
        "config_rule": match.get("rule"),
        "reason": "No provable higher-priority conflicting user-config rule",
    }


def _archive_id(policy: str, line: str, config_blob_sha: str) -> str:
    raw = policy.upper() + "|" + line + "|" + config_blob_sha
    return "cfg-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def sync(root: Path = ROOT, restore_ids: list[str] | None = None, now: str | None = None) -> dict:
    root = Path(root)
    rules_dir = root / "rulesets"
    config_path = root / "shadowrocket" / "ss.conf"
    archive_path = rules_dir / "config_conflict_archive.json"
    report_json = root / "reports" / "ruleset-config-conflict-sync.json"
    report_md = root / "reports" / "ruleset-config-conflict-sync.md"
    timestamp = now or datetime.now(timezone.utc).isoformat()

    config_bytes = config_path.read_bytes()
    config_text = config_bytes.decode("utf-8-sig")
    boundary = first_ruleset_line(config_text)
    if boundary is None:
        raise ValueError("no RULE-SET boundary found; refusing to infer config priority")
    prior_rules = prior_rule_lines(config_text)
    skip_entries = parse_skip_proxy(config_text)
    config_blob_sha = hashlib.sha1(
        b"blob " + str(len(config_bytes)).encode("ascii") + bytes([0]) + config_bytes
    ).hexdigest()

    expected = {policy.lower() + ".list" for policy in POLICIES}
    actual = {path.name for path in rules_dir.glob("*.list")}
    if actual != expected:
        raise ValueError("rule-set directory must contain exactly direct.list, proxy.list and reject.list")

    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {
        "schema_version": 1, "items": []
    }
    if not isinstance(archive.get("items"), list):
        raise ValueError("config conflict archive has invalid items structure")

    active_by_key = {
        (str(item.get("policy", "")).upper(), str(item.get("rule", ""))): item
        for item in archive["items"] if not item.get("restored_at")
    }
    removed = []
    suppressed_active_archive = []
    published_removed = 0
    pending_removed = 0
    archive_changed = False
    queue_changed = False
    retained_review = []
    restored = []
    restore_refused = []
    before_counts = {}
    after_counts = {}
    rule_lines: dict[str, set[str]] = {}
    queue_path = rules_dir / "pending_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else {
        "schema_version": 1, "max_published_rules": 30000, "queued_count": 0, "items": []
    }
    if not isinstance(queue.get("items"), list):
        raise ValueError("pending queue has invalid items structure")

    for policy in POLICIES:
        path = rules_dir / (policy.lower() + ".list")
        lines = {
            raw.strip() for raw in path.read_text(encoding="utf-8").splitlines()
            if raw.strip() and not raw.strip().startswith("#")
        }
        before_counts[policy] = len(lines)
        rule_lines[policy] = lines

    def archive_conflict(policy: str, line: str, result: dict, origin: str) -> None:
        nonlocal archive_changed
        key = (policy, line)
        if key in active_by_key:
            return
        item = {
            "id": _archive_id(policy, line, config_blob_sha),
            "policy": policy,
            "rule": line,
            "domain": result["domain"],
            "scope": result["scope"],
            "origin": origin,
            "removed_at": timestamp,
            "config_blob_sha": config_blob_sha,
            "config_rule_line": result.get("config_line"),
            "config_rule": result.get("config_rule"),
            "effective_config_policy": result.get("effective_policy"),
            "reason": result["reason"],
            "restored_at": None,
        }
        archive["items"].append(item)
        active_by_key[key] = item
        removed.append(item)
        archive_changed = True

    # Explicit restoration is opt-in and is rechecked against the current config.
    for restore_id in restore_ids or []:
        item = next(
            (x for x in archive["items"] if x.get("id") == restore_id and not x.get("restored_at")),
            None,
        )
        if item is None:
            restore_refused.append({"id": restore_id, "reason": "archive ID not found or already restored"})
            continue
        policy = str(item.get("policy", "")).upper()
        line = str(item.get("rule", ""))
        if policy not in POLICIES:
            restore_refused.append({"id": restore_id, "reason": "invalid archived policy"})
            continue
        try:
            result = classify_rule(policy, line, prior_rules, skip_entries)
        except ValueError as exc:
            restore_refused.append({"id": restore_id, "reason": str(exc)})
            continue
        if result["status"] != "NO_CONFLICT":
            restore_refused.append({
                "id": restore_id,
                "reason": "current config still conflicts or the overlap is unresolved",
                "current_status": result["status"],
                "config_rule": result.get("config_rule"),
            })
            continue
        total = sum(len(values) for values in rule_lines.values())
        if item.get("origin") == "pending_queue" or total >= 30000:
            kind, domain, scope = parse_rule_line(policy, line)
            queue.setdefault("items", []).append({
                "policy": policy,
                "scope": scope,
                "domain": domain,
                "queued_at": timestamp,
                "priority": 0,
                "reason": "User-requested restoration of a config-conflict archive item",
            })
            destination = "priority_queue"
            queue_changed = True
        else:
            rule_lines[policy].add(line)
            destination = "published"
        archive_changed = True
        item["restored_at"] = timestamp
        item["restore_destination"] = destination
        restored.append({"id": restore_id, "policy": policy, "rule": line, "destination": destination})
        active_by_key.pop((policy, line), None)

    # Remove definite conflicts from published lists; ambiguous matches are retained and reported.
    for policy in POLICIES:
        for line in sorted(list(rule_lines[policy])):
            if (policy, line) in active_by_key:
                rule_lines[policy].remove(line)
                published_removed += 1
                suppressed_active_archive.append({"policy": policy, "rule": line, "origin": "published_ruleset"})
                continue
            result = classify_rule(policy, line, prior_rules, skip_entries)
            if result["status"] == "CONFLICT":
                rule_lines[policy].remove(line)
                published_removed += 1
                archive_conflict(policy, line, result, "published_ruleset")
            elif result["status"] == "REVIEW":
                retained_review.append({"policy": policy, "rule": line, **result})

    # Apply the same precedence filter to queued rules so they cannot be promoted later.
    kept_queue = []
    for queued in queue.get("items", []):
        policy = str(queued.get("policy", "")).upper()
        scope = str(queued.get("scope", "exact_candidate"))
        domain = str(queued.get("domain", "")).lower().rstrip(".")
        if policy not in POLICIES or scope not in {"exact_candidate", "suffix_candidate"} or not domain:
            raise ValueError("invalid item in pending queue; refusing to discard or rewrite it")
        line = make_rule(policy, scope, domain)
        if (policy, line) in active_by_key:
            pending_removed += 1
            queue_changed = True
            suppressed_active_archive.append({"policy": policy, "rule": line, "origin": "pending_queue"})
            continue
        result = classify_rule(policy, line, prior_rules, skip_entries)
        if result["status"] == "CONFLICT":
            pending_removed += 1
            queue_changed = True
            archive_conflict(policy, line, result, "pending_queue")
        else:
            if result["status"] == "REVIEW":
                retained_review.append({"policy": policy, "rule": line, "origin": "pending_queue", **result})
            kept_queue.append(queued)
    if len(kept_queue) != len(queue.get("items", [])):
        queue_changed = True
    queue["items"] = kept_queue
    queue["queued_count"] = len(kept_queue)

    for policy in POLICIES:
        after_counts[policy] = len(rule_lines[policy])
        path = rules_dir / (policy.lower() + ".list")
        lines = sorted(rule_lines[policy])
        new_text = "\n".join(lines) + ("\n" if lines else "")
        if path.read_text(encoding="utf-8") != new_text:
            path.write_text(new_text, encoding="utf-8")

    if archive_changed:
        archive["updated_at"] = timestamp
        archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if queue_changed:
        queue["updated_at"] = timestamp
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "schema_version": 1,
        "completed_at": timestamp,
        "config_path": "shadowrocket/ss.conf",
        "config_read_only": True,
        "config_blob_sha": config_blob_sha,
        "first_ruleset_line": boundary,
        "higher_priority_rule_count": len(prior_rules),
        "published_before": before_counts,
        "published_after": after_counts,
        "published_removed_count": published_removed,
        "published_added_count": len(restored) - sum(1 for x in restored if x.get("destination") == "priority_queue"),
        "removed": removed,
        "removed_count": published_removed + pending_removed,
        "pending_queue_removed_count": pending_removed,
        "suppressed_active_archive": suppressed_active_archive,
        "retained_for_review": retained_review,
        "retained_for_review_count": len(retained_review),
        "restored": restored,
        "restore_refused": restore_refused,
        "active_archive_count": sum(1 for x in archive["items"] if not x.get("restored_at")),
        "policy": "Only provable first-match policy conflicts and non-DIRECT skip-proxy conflicts are removed. Same-policy overlaps are retained. Keyword/regex/conditional or otherwise unresolved overlaps are retained and reported; no speculative deletion is allowed.",
        "errors": [],
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# RULE-SET / ss.conf conflict synchronization",
        "",
        "- Config: " + report["config_path"] + " (read-only)",
        "- Config blob SHA: " + config_blob_sha,
        "- Higher-priority config rules inspected: " + str(len(prior_rules)),
        "- Published rules removed: " + str(report["published_removed_count"]),
        "- Pending queue entries removed: " + str(report["pending_queue_removed_count"]),
        "- Ambiguous overlaps retained for review: " + str(report["retained_for_review_count"]),
        "- Restored: " + str(len(restored)),
        "",
        "## Removed rules",
    ]
    lines.extend(
        "- " + x["id"] + " | " + x["policy"] + " | " + x["rule"] + " | config line "
        + str(x.get("config_rule_line")) + ": " + str(x.get("config_rule")) + " | " + x["reason"]
        for x in removed
    ) if removed else lines.append("- None")
    lines.extend(["", "## Already archived entries suppressed"])
    lines.extend("- " + x["policy"] + " | " + x["rule"] + " | " + x["origin"] for x in suppressed_active_archive) if suppressed_active_archive else lines.append("- None")
    lines.extend(["", "## Retained ambiguous overlaps"])
    lines.extend(
        "- " + x["policy"] + " | " + x["rule"] + " | " + x["status"] + " | " + x["reason"]
        for x in retained_review
    ) if retained_review else lines.append("- None")
    lines.extend(["", "## Restoration"])
    lines.extend(
        "- Restored " + x["id"] + " to " + x["destination"] + ": " + x["rule"]
        for x in restored
    ) if restored else lines.append("- None")
    lines.extend("- Refused " + x["id"] + ": " + x["reason"] for x in restore_refused)
    lines.extend([
        "",
        "The script never writes to shadowrocket/ss.conf. A config-conflict archive entry is not restored automatically; restoration is opt-in and rechecked against the current config.",
        "",
    ])
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    ids = [x.strip() for x in os.environ.get("RULESET_CONFIG_RESTORE_IDS", "").split(",") if x.strip()]
    report = sync(restore_ids=ids)
    print(json.dumps({
        "removed_count": report["removed_count"],
        "published_removed_count": report["published_removed_count"],
        "pending_queue_removed_count": report["pending_queue_removed_count"],
        "retained_for_review_count": report["retained_for_review_count"],
        "restored_count": len(report["restored"]),
        "config_read_only": report["config_read_only"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
