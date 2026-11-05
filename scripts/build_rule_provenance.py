#!/usr/bin/env python3
"""Build an append-only, deterministic rule-to-source evidence ledger.

A source snapshot hash proves which file version was evaluated, not a precise
upstream line number. Missing line-level evidence is explicitly left unknown.
"""
from __future__ import annotations

import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from json_document_store import read_document, write_document

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "sources/domain_reviews.json"
REGISTRY = ROOT / "sources/domain_sources.json"
SNAPSHOT = ROOT / "data/candidates.json"
PUBLISHED = ROOT / "rulesets"
PENDING = PUBLISHED / "pending_queue.json"
DELETION_ARCHIVE = PUBLISHED / "deletion_archive.json"
CONFLICT_ARCHIVE = PUBLISHED / "config_conflict_archive.json"
OUTPUT = ROOT / "sources/rule_provenance.json"
POLICIES = {"DIRECT", "PROXY", "REJECT"}

def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def rule_id(policy, scope, domain):
    raw = "|".join((policy, scope, domain)).encode()
    return hashlib.sha256(raw).hexdigest()[:20]

def published_map():
    result = {}
    for policy in sorted(POLICIES):
        path = PUBLISHED / (policy.lower() + ".list")
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DOMAIN,"):
                scope, domain = "exact_candidate", line[7:].lower()
            elif line.startswith("DOMAIN-SUFFIX,"):
                scope, domain = "suffix_candidate", line[14:].lower()
            else:
                raise ValueError("unsupported published rule in provenance builder: " + line)
            result[(policy, scope, domain)] = True
    return result

def archived_ids(path):
    data = read_json(path, {"items": []})
    result = {}
    for item in data.get("items", []):
        policy = str(item.get("policy", "")).upper()
        line = str(item.get("rule", ""))
        if line.startswith("DOMAIN,"):
            scope, domain = "exact_candidate", line[7:].lower()
        elif line.startswith("DOMAIN-SUFFIX,"):
            scope, domain = "suffix_candidate", line[14:].lower()
        else:
            continue
        if policy in POLICIES:
            result[(policy, scope, domain)] = item
    return result

def pending_map():
    data = read_json(PENDING, {"items": []})
    result = {}
    for item in data.get("items", []):
        policy = str(item.get("policy", "")).upper()
        scope = str(item.get("scope", item.get("source_entry_type", "exact_candidate")))
        domain = str(item.get("domain", "")).lower()
        if policy in POLICIES and scope in {"exact_candidate", "suffix_candidate"} and domain:
            result[(policy, scope, domain)] = item
    return result

def evidence_is_current(ev, source_map, snapshot_hashes, policy):
    sid = str(ev.get("source_id", ""))
    src = source_map.get(sid)
    if not src or src.get("enabled", True) is False:
        return False
    return (
        ev.get("currently_listed") is True
        and ev.get("sha256") == snapshot_hashes.get(sid)
        and ev.get("url") == src.get("url")
        and ev.get("publisher") == src.get("publisher")
        and ev.get("independence_group") == src.get("independence_group")
        and str(ev.get("classification", "")).upper() == policy
        and str(src.get("classification", "")).upper() == policy
        and ev.get("lineage_status") == src.get("lineage_status")
        and ev.get("policy_evidence", "documented_policy") == src.get("policy_evidence", "documented_policy")
        and ev.get("upstream_repositories", []) == src.get("upstream_repositories", [])
        and ev.get("entry_type") in {"exact_candidate", "suffix_candidate"}
    )

def build(review_data, registry_data, snapshot_data, previous, published, pending, deleted, conflicts, now):
    source_map = {x["id"]: x for x in registry_data.get("sources", [])}
    snapshot_hashes = {x["id"]: x["sha256"] for x in snapshot_data.get("sources", []) if x.get("id") and x.get("sha256")}
    prior = {x["rule_id"]: x for x in previous.get("rules", []) if x.get("rule_id")}
    current = {}
    for item in review_data.get("reviews", []):
        domain = str(item.get("domain", "")).lower().rstrip(".")
        policy = str(item.get("policy", item.get("classification", ""))).upper()
        scope = str(item.get("source_entry_type", "exact_candidate"))
        if not domain or policy not in POLICIES or scope not in {"exact_candidate", "suffix_candidate"}:
            continue
        key = (policy, scope, domain)
        rid = rule_id(*key)
        valid = [ev for ev in item.get("evidence", []) if evidence_is_current(ev, source_map, snapshot_hashes, policy)]
        valid.sort(key=lambda x: (str(x.get("source_id", "")), str(x.get("sha256", ""))))
        sources = [{
            "source_id": ev["source_id"],
            "publisher": ev.get("publisher"),
            "independence_group": ev.get("independence_group"),
            "policy": policy,
            "source_file_url": ev.get("url"),
            "snapshot_sha256": ev.get("sha256"),
            "source_entry_scope": ev.get("entry_type"),
            "line_number": ev.get("line_number") if isinstance(ev.get("line_number"), int) and ev.get("line_number") > 0 else None,
            "evidence_grade": "exact_file_line" if isinstance(ev.get("line_number"), int) and ev.get("line_number") > 0 else "snapshot_membership",
            "lineage_status": ev.get("lineage_status", "unverified"),
        } for ev in valid]
        if key in published:
            state = "published"
        elif key in pending:
            state = "pending"
        elif key in deleted:
            state = "lifecycle_archived"
        elif key in conflicts:
            state = "config_conflict_archived"
        elif item.get("status") == "APPROVED":
            state = "approved_not_published"
        else:
            state = str(item.get("status", "review")).lower()
        old = prior.get(rid, {})
        signature = hashlib.sha256(json.dumps({
            "policy": policy, "scope": scope, "sources": sources, "state": state,
            "review_status": item.get("status")
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        history = list(old.get("history", []))
        if not history or old.get("signature") != signature:
            history.append({
                "observed_at": now, "state": state,
                "review_status": item.get("status"),
                "evidence_source_ids": [x["source_id"] for x in sources],
                "signature": signature
            })
        current[rid] = {
            "rule_id": rid, "domain": domain, "policy": policy, "scope": scope,
            "state": state, "review_status": item.get("status"),
            "confidence": item.get("confidence"),
            "first_seen": old.get("first_seen") or item.get("first_seen") or item.get("reviewed_at") or now,
            "last_seen": now, "sources": sources, "history": history,
            "signature": signature,
            "lineage_interpretation": "Publisher lineage is separate metadata; unverified lineage does not erase current file-membership evidence.",
        }
    # Preserve historical rules no longer present in the review ledger; never silently erase provenance.
    for rid, old in prior.items():
        if rid not in current:
            old = dict(old)
            old["currently_reviewed"] = False
            old["last_seen"] = old.get("last_seen")
            current[rid] = old
        else:
            current[rid]["currently_reviewed"] = True
    return {
        "schema_version": 1,
        "generated_at": now,
        "method": "review-ledger evidence joined to exact configured source identity and current source snapshot SHA-256",
        "rule_count": len(current),
        "source_snapshot_hashes": dict(sorted(snapshot_hashes.items())),
        "evidence_limits": {
            "line_number": "Current collection records original upstream line numbers for supported formats. Null is retained only for legacy evidence or entries without a recoverable original line; it is not represented as exact-file-line proof.",
            "lineage": "Repository-wide README/source references are not item-level ancestry and do not independently verify a rule's upstream origin."
        },
        "rules": sorted(current.values(), key=lambda x: x["rule_id"])
    }

def main():
    now = datetime.now(timezone.utc).isoformat()
    result = build(
        read_document(REVIEWS, "reviews", {"reviews": []}),
        read_json(REGISTRY, {"sources": []}),
        read_document(SNAPSHOT, "candidates", {"sources": [], "candidates": []}),
        read_document(OUTPUT, "rules", {"rules": []}),
        published_map(), pending_map(),
        archived_ids(DELETION_ARCHIVE), archived_ids(CONFLICT_ARCHIVE), now
    )
    write_document(OUTPUT, result, "rules")
    print(f"Rule provenance ledger: {result['rule_count']} rules; source snapshots: {len(result['source_snapshot_hashes'])}; output: {OUTPUT.relative_to(ROOT)}")

if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
