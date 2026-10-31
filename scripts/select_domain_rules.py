#!/usr/bin/env python3
"""Conservative selector for externally sourced domain candidates.

The canonical Shadowrocket config is read-only and authoritative. External data
never supplies a policy. Only explicit entries in policy_approvals.json may
produce exact DOMAIN rules, and output is written to reports/ only.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
APPROVALS = ROOT / "sources" / "policy_approvals.json"
REPORT = ROOT / "reports" / "rule-selector-audit.md"
OUTPUT = ROOT / "reports" / "approved-domain-rules.list"
SOURCE_URL = (
    "https://raw.githubusercontent.com/ithtelab/sr-adblock/"
    "release/ruleset/ad-domain-lite.list"
)
EXPECTED_GIT_BLOB_SHA1 = "ec23c2d1280ea4a59717816716b8ccb569dac624"
EXPECTED_ENTRIES = 56516
MAX_BYTES = 2_000_000
POLICIES = {"DIRECT", "PROXY", "REJECT"}
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def ancestors(domain: str):
    labels = domain.split(".")
    for i in range(len(labels)):
        yield ".".join(labels[i:])


def load_candidates() -> dict[str, bool]:
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "Shadowrocket-rule-selector/1.0"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            fail(f"unexpected source response: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        fail("external source exceeds 2 MB")
    actual = blob_sha1(data)
    if actual != EXPECTED_GIT_BLOB_SHA1:
        fail(f"source drift: expected {EXPECTED_GIT_BLOB_SHA1}, received {actual}; manual review required")

    candidates: dict[str, bool] = {}
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value != raw or any(ch.isspace() for ch in value):
            fail(f"invalid whitespace at source line {number}")
        is_suffix = value.startswith(".")
        domain = value[1:] if is_suffix else value
        if not DOMAIN_RE.fullmatch(domain):
            fail(f"invalid domain at source line {number}: {raw!r}")
        key = domain.lower()
        if key in candidates:
            fail(f"duplicate candidate at source line {number}: {key}")
        candidates[key] = is_suffix
    if len(candidates) != EXPECTED_ENTRIES:
        fail(f"candidate count mismatch: expected {EXPECTED_ENTRIES}, got {len(candidates)}")
    return candidates


def load_existing() -> list[tuple[str, str, str, int]]:
    if not CONFIG.is_file():
        fail("canonical shadowrocket/ss.conf is missing")
    text = CONFIG.read_text(encoding="utf-8")
    if text.count("[Rule]") != 1 or text.count("[Host]") != 1:
        fail("cannot uniquely isolate canonical [Rule] section")
    block = text.split("[Rule]", 1)[1].split("[Host]", 1)[0]
    rules = []
    for line_no, raw in enumerate(block.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 3:
            continue
        kind, value, policy = fields[0].upper(), fields[1].lower().lstrip("."), fields[-1].upper()
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX"} or policy not in POLICIES:
            continue
        if DOMAIN_RE.fullmatch(value):
            rules.append((kind, value, policy, line_no))
    return rules


def overlaps(domain: str, candidate_is_suffix: bool, rules):
    hits = []
    for kind, value, policy, line_no in rules:
        covered = False
        if kind == "DOMAIN-SUFFIX":
            covered = domain == value or domain.endswith("." + value)
            if candidate_is_suffix:
                covered = covered or value.endswith("." + domain)
        elif kind == "DOMAIN":
            covered = domain == value or (candidate_is_suffix and value.endswith("." + domain))
        if covered:
            hits.append((kind, value, policy, line_no))
    return hits


def load_approvals(candidates: dict[str, bool]) -> dict[str, dict[str, str]]:
    if not APPROVALS.is_file():
        fail("sources/policy_approvals.json is missing")
    try:
        payload = json.loads(APPROVALS.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"approval manifest is invalid: {exc}")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("approvals"), list):
        fail("approval manifest schema is invalid")
    approvals = {}
    for item in payload["approvals"]:
        if not isinstance(item, dict):
            fail("each approval must be an object")
        domain = str(item.get("domain", "")).lower().strip()
        policy = str(item.get("policy", "")).upper().strip()
        evidence = str(item.get("evidence", "")).strip()
        if not DOMAIN_RE.fullmatch(domain):
            fail(f"invalid approved domain: {domain!r}")
        if domain not in candidates:
            fail(f"approved domain is not in the pinned candidate source: {domain}")
        if policy not in POLICIES:
            fail(f"unsupported policy for {domain}: {policy}")
        if not evidence:
            fail(f"approval requires an evidence note: {domain}")
        if domain in approvals:
            fail(f"duplicate approval: {domain}")
        approvals[domain] = {"policy": policy, "evidence": evidence}
    return approvals


def self_test() -> None:
    sample = [
        ("DOMAIN-SUFFIX", "example.com", "PROXY", 1),
        ("DOMAIN", "ads.example.net", "REJECT", 2),
        ("DOMAIN-SUFFIX", "conflict.test", "DIRECT", 3),
        ("DOMAIN-SUFFIX", "conflict.test", "PROXY", 4),
    ]
    assert len(overlaps("api.example.com", False, sample)) == 1
    assert overlaps("example.com", False, sample)[0][2] == "PROXY"
    assert overlaps("ads.example.net", False, sample)[0][2] == "REJECT"
    assert {x[2] for x in overlaps("x.conflict.test", False, sample)} == {"DIRECT", "PROXY"}
    assert overlaps("new.test", False, sample) == []
    print("PASS: selector overlap self-tests")


def main() -> None:
    import sys
    if "--self-test" in sys.argv:
        self_test()
        return

    candidates = load_candidates()
    existing = load_existing()
    approvals = load_approvals(candidates)

    stats = defaultdict(int)
    conflicts = []
    pending = []
    generated = []
    for domain, is_suffix in candidates.items():
        hits = overlaps(domain, is_suffix, existing)
        policies = {hit[2] for hit in hits}
        approval = approvals.get(domain)

        if len(policies) > 1:
            stats["multi_policy_conflict"] += 1
            conflicts.append((domain, "multi-policy", sorted(policies)))
            continue
        if policies & {"DIRECT", "PROXY"}:
            stats["routing_scope_overlap"] += 1
            conflicts.append((domain, "DIRECT/PROXY scope", sorted(policies)))
            continue
        if policies == {"REJECT"}:
            stats["already_rejected"] += 1
            continue
        if approval is None:
            stats["unreviewed"] += 1
            pending.append(domain)
            continue
        if hits and policies == {approval["policy"]}:
            stats["already_present_same_policy"] += 1
            continue
        if hits:
            stats["approval_conflict"] += 1
            conflicts.append((domain, "approval differs from existing policy", sorted(policies)))
            continue
        # Deliberately emit exact DOMAIN only. A source suffix marker does not
        # authorize widening a rule to all subdomains.
        generated.append(f"DOMAIN,{domain},{approval['policy']}")
        stats["approved_new_rules"] += 1

    generated.sort()
    conflicts.sort()
    pending.sort()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(generated) + ("\n" if generated else ""), encoding="utf-8")

    report = [
        "# Domain rule selector audit",
        "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Pinned source SHA-1: `{EXPECTED_GIT_BLOB_SHA1}`",
        f"- Candidate count: {len(candidates)}",
        f"- Existing DOMAIN / DOMAIN-SUFFIX rules examined: {len(existing)}",
        f"- Explicit approvals: {len(approvals)}",
        "",
        "## Results",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for key in ("already_present_same_policy", "already_rejected", "routing_scope_overlap",
                "multi_policy_conflict", "approval_conflict", "unreviewed", "approved_new_rules"):
        report.append(f"| {key} | {stats[key]} |")
    report += [
        "",
        "## Conflict review queue",
        "",
        "| Candidate | Conflict type | Existing policies |",
        "|---|---|---|",
    ]
    report += [f"| `{domain}` | {kind} | {', '.join(policies)} |" for domain, kind, policies in conflicts]
    report += [
        "",
        "## Unreviewed candidates",
        "",
        f"Unreviewed candidates: {len(pending)}. They are not assigned a policy and are not emitted.",
        "",
        "## Output contract",
        "",
        "- The only generated rule form is `DOMAIN,<domain>,DIRECT|PROXY|REJECT`.",
        "- A source leading dot never authorizes DOMAIN-SUFFIX output; only exact DOMAIN rules are emitted.",
        "- No policy is inferred from the upstream list.",
        "- DIRECT/PROXY overlaps and multi-policy collisions are quarantined.",
        "- Existing config, DNS settings, nodes, rule order, and subscription are never modified.",
        "- Generated rules are an approval-gated report artifact, not an automatic config patch.",
        "",
        f"Generated rules file: `{OUTPUT.relative_to(ROOT)}` ({len(generated)} rules)",
        "",
    ]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
