#!/usr/bin/env python3
"""Deterministically activate stable, policy-evidenced public domain sources."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from source_registry import validate_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources/domain_sources.json"
MATRIX = ROOT / "sources/source_candidates.json"
LOG = ROOT / "sources/source_activation_log.json"
REPORT = ROOT / "reports/source-activation.md"
POLICIES = {"DIRECT", "PROXY", "REJECT"}
FORMATS = {"domain-only", "adblock-domain-rules", "shadowrocket-domain-rules", "quantumult-domain-rules"}
STRONG_EVIDENCE = {"explicit_third_field", "README_RULE-SET_reference", "README_policy_reference"}
MIN_UNIQUE_DOMAINS = 100
WEIGHT = 0.4


def source_id_for(repository: str, policy: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", repository.lower().replace("/", "-")).strip("-")
    suffix = hashlib.sha256((repository + "|" + policy).encode("utf-8")).hexdigest()[:8]
    return ("auto-" + slug)[:68] + "-" + suffix


def candidate_file(candidate: dict) -> dict | None:
    eligible = []
    for item in candidate.get("files", []):
        url = urlparse(str(item.get("url", "")))
        evidence = item.get("policy_evidence")
        drift = item.get("drift", {})
        unique_count = int(item.get("domain_fingerprint_count", 0))
        if item.get("parser") not in FORMATS:
            continue
        if evidence not in STRONG_EVIDENCE or drift.get("status") != "unchanged":
            continue
        if unique_count < MIN_UNIQUE_DOMAINS:
            continue
        if url.scheme != "https" or url.hostname != "raw.githubusercontent.com":
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            continue
        eligible.append(item)
    if not eligible:
        return None
    return sorted(eligible, key=lambda x: (-int(x.get("domain_fingerprint_count", 0)), x["url"]))[0]


def activate(registry: dict, matrix: dict, now: str | None = None) -> tuple[dict, list[dict], list[dict]]:
    timestamp = now or datetime.now(timezone.utc).isoformat()
    existing = validate_registry(registry)
    existing_publishers = {
        (str(source.get("classification", "")).upper(), str(source.get("publisher", "")))
        for source in existing.values()
    }
    existing_urls = {str(source.get("url", "")) for source in existing.values()}
    activated = []
    decisions = []
    sources = registry.setdefault("sources", [])
    weights = registry.setdefault("scoring", {}).setdefault("source_weights", {})

    for candidate in matrix.get("candidates", []):
        policy = str(candidate.get("policy", "")).upper()
        repository = str(candidate.get("repository", "")).strip()
        if policy not in POLICIES or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            continue
        if not candidate.get("activation_eligible") or candidate.get("archived"):
            decisions.append({"repository": repository, "policy": policy, "decision": "held", "reason": "policy evidence is not strong or publisher is archived"})
            continue
        selected = candidate_file(candidate)
        if selected is None:
            decisions.append({"repository": repository, "policy": policy, "decision": "held", "reason": "no supported file with 100+ unique domains and an unchanged second observation"})
            continue
        url = str(selected["url"])
        if (policy, repository) in existing_publishers or url in existing_urls:
            decisions.append({"repository": repository, "policy": policy, "decision": "already_registered", "reason": "publisher or URL is already registered"})
            continue
        sid = source_id_for(repository, policy)
        if sid in existing:
            decisions.append({"repository": repository, "policy": policy, "decision": "already_registered", "reason": "deterministic source ID already exists"})
            continue
        evidence = str(selected["policy_evidence"])
        source = {
            "id": sid,
            "publisher": repository,
            "role": "primary_candidate_source",
            "url": url,
            "format": selected["parser"],
            "weight": WEIGHT,
            "classification": policy,
            "minimum_entries": MIN_UNIQUE_DOMAINS,
            "independence_group": repository,
            "lineage_status": "unverified",
            "policy_evidence": "explicit_action" if evidence == "explicit_third_field" else "documented_policy",
            "upstream_repositories": [],
            "lineage_note": "Automatically admitted by deterministic parser, policy-evidence, publisher, size and two-observation stability gates. Lineage remains unverified; shared README references and domain overlap are correlation warnings, not automatic vetoes.",
            "bootstrap_enqueue": True,
            "auto_activation": {
                "engine": "deterministic-source-admission/1.0",
                "activated_at": timestamp,
                "candidate_domain_count": int(selected.get("domain_count", 0)),
                "unique_domain_count": int(selected.get("domain_fingerprint_count", 0)),
                "domain_set_sha256": candidate.get("domain_set_sha256"),
                "policy_evidence_source": evidence,
                "lineage_warning": candidate.get("lineage_warning"),
                "shared_readme_reference_peer_count": len(candidate.get("readme_shared_reference_peers", []))
            }
        }
        sources.append(source)
        weights[sid] = WEIGHT
        existing[sid] = source
        existing_publishers.add((policy, repository))
        existing_urls.add(url)
        activated.append({"id": sid, "repository": repository, "policy": policy, "url": url, "unique_domains": int(selected.get("domain_fingerprint_count", 0))})
        decisions.append({"repository": repository, "policy": policy, "decision": "activated", "reason": "strong policy evidence, non-archived publisher, supported parser, 100+ unique domains and unchanged second observation", "source_id": sid})

    validate_registry(registry)
    return registry, activated, decisions


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    registry, activated, decisions = activate(registry, matrix)
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prior = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {"schema_version": 1, "activations": []}
    known = {x.get("id") for x in prior.get("activations", [])}
    prior["activations"].extend(x for x in activated if x["id"] not in known)
    prior["last_evaluated_at"] = datetime.now(timezone.utc).isoformat()
    prior["last_decisions"] = decisions
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(prior, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Deterministic source admission",
        "",
        "No AI/LLM is used. Admission requires a supported parser, strong explicit/documented policy evidence, a non-archived publisher, at least 100 unique domains, and an unchanged second observation.",
        "Lineage gaps, shared README references and domain-set overlap are recorded as correlation warnings, not blanket vetoes. Per-domain publication still requires matching evidence from distinct publishers and source groups.",
        "",
        f"- Newly activated this run: **{len(activated)}**",
        f"- Candidate decisions: **{len(decisions)}**",
        "",
        "## Decisions",
        ""
    ]
    for item in decisions:
        lines.append(f"- {item['decision']}: {item['repository']} / {item['policy']} — {item['reason']}")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"activated": activated, "decisions": decisions}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
