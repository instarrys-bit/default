#!/usr/bin/env python3
"""Assess discovered rule-list URLs for parser compatibility and explicit policy semantics.

This is a non-activating gate: it never edits the trusted source registry.
"""
from __future__ import annotations
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "sources/discovered_sources.json"
OUTPUT = ROOT / "sources/source_assessments.json"
REPORT = ROOT / "reports/source-assessment.md"
MAX_BYTES = 2_000_000
MAX_URLS = 50
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
DOMAIN_RULE_RE = re.compile(r"^(DOMAIN|DOMAIN-SUFFIX),([^,\s]+)(?:,([^,\s]+))?$", re.I)
QX_DOMAIN_RULE_RE = re.compile(r"^(HOST|HOST-SUFFIX),([^,\s]+),([^,\s]+)$", re.I)
ADBLOCK_RE = re.compile(r"^\|\|([a-z0-9.-]+)\^")
SENSITIVE_PATH_RE = re.compile(r"(?:porn|adult|nsfw|xxx|sex[-_]?content)", re.I)

def fetch_raw(url: str, repository: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("assessment accepts only HTTPS raw.githubusercontent.com URLs")
    parts = [x for x in parsed.path.split("/") if x]
    if len(parts) < 4 or "/".join(parts[:2]).lower() != repository.lower():
        raise ValueError("rule-list URL does not belong to the declared repository")
    if SENSITIVE_PATH_RE.search(parsed.path):
        raise ValueError("sensitive path is excluded from assessment")
    request = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-Source-Assessor/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        final = urllib.parse.urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise ValueError("unexpected rule-list response")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("rule-list exceeds assessment size limit")
    return data

def readme_policy_claim(readme: str, url: str) -> list[str]:
    actions = set()
    escaped = re.escape(url)
    for match in re.finditer(r"RULE-SET\s*,\s*" + escaped + r"\s*,\s*(DIRECT|PROXY|REJECT)\b", readme, re.I):
        actions.add(match.group(1).upper())
    return sorted(actions)

def assess_payload(payload: bytes, url: str, policy_claims: list[str]) -> dict:
    lines = payload.decode("utf-8-sig", errors="replace").splitlines()
    substantive = [line.split("#", 1)[0].strip() for line in lines]
    substantive = [line for line in substantive if line and not line.startswith(("!", "#", "["))]
    exact = set()
    suffix = set()
    actions = {}
    keyword_count = 0
    ip_count = 0
    domain_rule_lines = 0
    action_line_count = 0
    qx_domain_rule_lines = 0
    duplicate_domain_lines = 0
    adblock = set()
    domain_only = set()
    for line in substantive:
        match = DOMAIN_RULE_RE.fullmatch(line)
        if match:
            kind, domain, action = match.groups()
            domain = domain.lower().rstrip(".")
            if not DOMAIN_RE.fullmatch(domain):
                continue
            target = exact if kind.upper() == "DOMAIN" else suffix
            if domain in exact or domain in suffix:
                duplicate_domain_lines += 1
            target.add(domain)
            domain_rule_lines += 1
            if action:
                action = action.upper()
                if action in {"DIRECT", "PROXY", "REJECT"}:
                    action_line_count += 1
                    actions[action] = actions.get(action, 0) + 1
                else:
                    actions["UNSUPPORTED"] = actions.get("UNSUPPORTED", 0) + 1
            continue
        qx = QX_DOMAIN_RULE_RE.fullmatch(line)
        if qx:
            kind, domain, action = qx.groups()
            domain = domain.lower().rstrip(".")
            if DOMAIN_RE.fullmatch(domain):
                target = exact if kind.upper() == "HOST" else suffix
                if domain in exact or domain in suffix:
                    duplicate_domain_lines += 1
                target.add(domain)
                domain_rule_lines += 1
                qx_domain_rule_lines += 1
                action = action.upper()
                if action == "OUTSIDE":
                    action = "PROXY"
                if action in {"DIRECT", "PROXY", "REJECT"}:
                    action_line_count += 1
                    actions[action] = actions.get(action, 0) + 1
                else:
                    actions["UNSUPPORTED"] = actions.get("UNSUPPORTED", 0) + 1
            continue
        if line.upper().startswith(("DOMAIN-KEYWORD,", "HOST-KEYWORD,")):
            keyword_count += 1
            continue
        if line.upper().startswith(("IP-CIDR,", "IP-CIDR6,", "IP-ASN,")):
            ip_count += 1
            continue
        ad = ADBLOCK_RE.match(line.lower())
        if ad and DOMAIN_RE.fullmatch(ad.group(1).rstrip(".")):
            adblock.add(ad.group(1).rstrip("."))
            continue
        if DOMAIN_RE.fullmatch(line.lower().lstrip(".")):
            domain_only.add(line.lower().lstrip("."))
    domain_rule_count = len(exact) + len(suffix)
    explicit_actions = {x for x in actions if x in {"DIRECT", "PROXY", "REJECT"}}
    complete_explicit_action = (
        domain_rule_lines > 0
        and action_line_count == domain_rule_lines
        and len(explicit_actions) == 1
        and "UNSUPPORTED" not in actions
    )
    header = " ".join(lines[:12]).lower()
    header_claims = set()
    if "代理列表" in header or "proxy list" in header:
        header_claims.add("PROXY")
    if "直连列表" in header or "direct list" in header:
        header_claims.add("DIRECT")
    if "拦截列表" in header or "blocklist" in header or "block list" in header:
        header_claims.add("REJECT")
    all_policy_claims = set(policy_claims) | header_claims
    if complete_explicit_action:
        all_policy_claims.add(next(iter(explicit_actions)))
    policy = None
    policy_evidence = "none"
    if len(all_policy_claims) == 1:
        policy = next(iter(all_policy_claims))
        if complete_explicit_action:
            policy_evidence = "explicit_third_field"
        elif policy_claims:
            policy_evidence = "README_policy_reference"
        elif header_claims:
            policy_evidence = "source_header_claim"
    elif len(all_policy_claims) > 1 or explicit_actions or "UNSUPPORTED" in actions:
        policy_evidence = "ambiguous"
    if len(adblock) >= 20 and len(adblock) >= len(exact) + len(suffix):
        parser = "adblock-domain-rules"
    elif qx_domain_rule_lines >= 20:
        parser = "quantumult-domain-rules"
    elif domain_rule_count >= 20:
        parser = "shadowrocket-domain-rules"
    elif len(domain_only) >= 20 and len(domain_only) >= len(substantive) * 0.8:
        parser = "domain-only"
    else:
        parser = "unsupported_or_too_small"
    return {
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "substantive_lines": len(substantive),
        "parser_candidate": parser,
        "exact_domain_count": len(exact),
        "suffix_domain_count": len(suffix),
        "adblock_domain_count": len(adblock),
        "domain_only_count": len(domain_only),
        "domain_fingerprints": sorted(
            hashlib.sha256(domain.encode("utf-8")).hexdigest()[:32]
            for domain in (exact | suffix | adblock | domain_only)
        ),
        "duplicate_domain_lines": duplicate_domain_lines,
        "domain_keyword_rules_ignored": keyword_count,
        "ip_asn_rules_ignored": ip_count,
        "explicit_action_counts": actions,
        "readme_policy_claims": policy_claims,
        "policy_candidate": policy,
        "policy_evidence": policy_evidence,
        "activation_eligible": False,
    }

def compare_drift(current: dict, previous: dict | None) -> dict:
    if current.get("error"):
        return {"status": "unavailable", "added_domain_count": 0, "removed_domain_count": 0, "policy_changed": False}
    if not previous:
        return {"status": "baseline_initialized", "added_domain_count": len(current.get("domain_fingerprints", [])), "removed_domain_count": 0, "policy_changed": False}
    old_sha = previous.get("sha256")
    new_sha = current.get("sha256")
    policy_changed = (
        previous.get("policy_candidate") != current.get("policy_candidate")
        or previous.get("policy_evidence") != current.get("policy_evidence")
    )
    if old_sha == new_sha:
        return {
            "status": "policy_metadata_changed" if policy_changed else "unchanged",
            "added_domain_count": 0,
            "removed_domain_count": 0,
            "policy_changed": policy_changed,
        }
    old_domains = set(previous.get("domain_fingerprints", []))
    new_domains = set(current.get("domain_fingerprints", []))
    if not old_domains:
        return {
            "status": "content_changed_baseline_schema_unavailable",
            "added_domain_count": None,
            "removed_domain_count": None,
            "policy_changed": policy_changed,
        }
    added = len(new_domains - old_domains)
    removed = len(old_domains - new_domains)
    status = "domain_set_changed" if added or removed else "content_changed_no_domain_change"
    if policy_changed:
        status += "_and_policy_changed"
    return {
        "status": status,
        "added_domain_count": added,
        "removed_domain_count": removed,
        "policy_changed": policy_changed,
        "previous_sha256": old_sha,
        "current_sha256": new_sha,
    }

def render_report(assessments: list[dict], drift_summary: dict | None = None) -> str:
    rows = [
        "# Automated source assessment",
        "",
        f"- Rule-list files assessed: **{len(assessments)}**",
        "- This stage checks syntax and explicit policy claims only. It never activates sources.",
        "- Keyword, IP/CIDR and ASN rules are counted as ignored; they are never converted into domains.",
        "",
        "| Repository | Parser candidate | Policy candidate | Domain entries | Drift | Evidence |",
        "|---|---|---|---:|---|---|",
    ]
    for item in assessments:
        rows.append(
            f"| {item['repository']} | {item['parser_candidate']} | "
            f"{item.get('policy_candidate') or '—'} | "
            f"{item['exact_domain_count'] + item['suffix_domain_count'] + item['adblock_domain_count'] + item['domain_only_count']} | "
            f"{item.get('drift', {}).get('status', 'not_compared')} | {item['policy_evidence']} |"
        )
    drift_summary = drift_summary or {}
    rows.extend([
        "",
        "## Source update drift",
        "",
        f"- New source files: {drift_summary.get('new_source_files', 0)}",
        f"- Changed source files: {drift_summary.get('changed_source_files', 0)}",
        f"- Added domain entries: {drift_summary.get('added_domain_count', 0)}",
        f"- Removed domain entries: {drift_summary.get('removed_domain_count', 0)}",
        f"- Policy changes: {drift_summary.get('policy_changes', 0)}",
        "",
        "## Assessment details",
        "",
    ])
    for item in assessments:
        rows.extend([
            f"### {item['repository']}",
            "",
            f"- URL: {item['url']}",
            f"- SHA-256: {item.get('sha256', 'unavailable')}",
            f"- Exact DOMAIN: {item['exact_domain_count']}; DOMAIN-SUFFIX: {item['suffix_domain_count']}; Adblock: {item['adblock_domain_count']}; domain-only: {item['domain_only_count']}; duplicate lines: {item.get('duplicate_domain_lines', 0)}",
            f"- Ignored non-domain rules: DOMAIN-KEYWORD {item['domain_keyword_rules_ignored']}; IP/CIDR/ASN {item['ip_asn_rules_ignored']}",
            f"- Explicit action counts: {json.dumps(item['explicit_action_counts'], sort_keys=True)}",
            f"- Policy evidence: {item['policy_evidence']}; candidate: {item.get('policy_candidate') or 'none'}",
            "",
        ])
    rows.extend([
        "## Activation gate",
        "",
        "A parser candidate is not a trusted source. Activation still requires declared policy semantics, independent publishers, lineage checks, parser tests, stable update history, and all per-policy confidence gates. This report is advisory and cannot alter sources/domain_sources.json.",
        "",
    ])
    return "\n".join(rows)

def main() -> int:
    discovery = json.loads(INPUT.read_text(encoding="utf-8"))
    previous_data = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"assessments": []}
    previous_by_url = {x.get("url"): x for x in previous_data.get("assessments", []) if x.get("url")}
    candidates = sorted(
        discovery.get("candidates", []),
        key=lambda item: (bool(item.get("seeded_source_urls")), int(item.get("stars", 0))),
        reverse=True,
    )
    assessments = []
    readme_cache = {}
    for candidate in candidates:
        repository = candidate.get("repository", "")
        seeded = set(candidate.get("seeded_source_urls", []))
        urls = sorted(candidate.get("rule_list_urls", []), key=lambda url: (url not in seeded, url))
        if not repository or not urls:
            continue
        owner, name = repository.split("/", 1)
        for url in urls:
            if len(assessments) >= MAX_URLS:
                break
            if SENSITIVE_PATH_RE.search(urllib.parse.urlparse(url).path):
                continue
            try:
                payload = fetch_raw(url, repository)
                claims = candidate.get("readme_policy_claims", {}).get(url, [])
                item = assess_payload(payload, url, claims)
                item["repository"] = repository
                item["stars"] = candidate.get("stars", 0)
                item["archived"] = candidate.get("archived", False)
                assessments.append(item)
            except (OSError, urllib.error.URLError, ValueError) as exc:
                assessments.append({
                    "repository": repository, "url": url,
                    "parser_candidate": "fetch_or_validation_error",
                    "policy_candidate": None, "policy_evidence": "none",
                    "error": str(exc), "activation_eligible": False,
                    "exact_domain_count": 0, "suffix_domain_count": 0,
                    "adblock_domain_count": 0, "domain_only_count": 0,
                    "duplicate_domain_lines": 0,
                    "domain_fingerprints": [],
                    "domain_keyword_rules_ignored": 0, "ip_asn_rules_ignored": 0,
                    "explicit_action_counts": {},
                })
    for item in assessments:
        item["drift"] = compare_drift(item, previous_by_url.get(item.get("url")))
    drift_summary = {
        "new_source_files": sum(1 for x in assessments if x.get("drift", {}).get("status") == "baseline_initialized"),
        "changed_source_files": sum(1 for x in assessments if x.get("drift", {}).get("status", "").startswith(("domain_set_changed", "content_changed"))),
        "added_domain_count": sum(x["drift"].get("added_domain_count") or 0 for x in assessments),
        "removed_domain_count": sum(x["drift"].get("removed_domain_count") or 0 for x in assessments),
        "policy_changes": sum(1 for x in assessments if x["drift"].get("policy_changed")),
    }
    result = {
        "schema_version": 1,
        "assessment_count": len(assessments),
        "drift_summary": drift_summary,
        "activation_count": 0,
        "assessments": assessments,
        "activation_policy": "Assessment never edits or enables sources/domain_sources.json.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(assessments, drift_summary), encoding="utf-8")
    print(json.dumps({
        "assessed": len(assessments),
        "parser_candidates": sum(1 for x in assessments if x.get("parser_candidate") in {"domain-only", "adblock-domain-rules", "shadowrocket-domain-rules", "quantumult-domain-rules"}),
        "policy_candidates": sum(1 for x in assessments if x.get("policy_candidate")),
        "activated": 0,
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
