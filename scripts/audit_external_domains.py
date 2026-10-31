#!/usr/bin/env python3
"""Read-only audit of a pinned external domain list against the canonical config.

No downloaded code is executed. This script never classifies candidates, rewrites
ss.conf, or publishes rules. It reports syntax, source drift, duplicates and
intersections with existing DOMAIN / DOMAIN-SUFFIX rules.
"""
from __future__ import annotations

import hashlib
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
SOURCE_URL = (
    "https://raw.githubusercontent.com/ithtelab/sr-adblock/"
    "release/ruleset/ad-domain-lite.list"
)
EXPECTED_GIT_BLOB_SHA1 = "ec23c2d1280ea4a59717816716b8ccb569dac624"
EXPECTED_ENTRIES = 56516
MAX_BYTES = 2_000_000
OUTPUT = ROOT / "reports" / "external-domain-audit.md"
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def ancestors(domain: str):
    labels = domain.split(".")
    for index in range(len(labels)):
        yield ".".join(labels[index:])


def main() -> int:
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "Shadowrocket-domain-audit/1.0"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise SystemExit(f"ERROR: unexpected download response: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("ERROR: source exceeds the 2 MB safety limit")

    actual_sha = git_blob_sha1(data)
    if actual_sha != EXPECTED_GIT_BLOB_SHA1:
        raise SystemExit(
            f"ERROR: upstream content changed; expected {EXPECTED_GIT_BLOB_SHA1}, "
            f"received {actual_sha}. Manual review required."
        )

    text = data.decode("utf-8")
    candidates: list[tuple[str, bool]] = []
    invalid: list[tuple[int, str]] = []
    seen: set[str] = set()
    duplicates: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value != raw or any(ch.isspace() for ch in value):
            invalid.append((number, raw))
            continue
        is_suffix = value.startswith(".")
        domain = value[1:] if is_suffix else value
        if not DOMAIN_RE.fullmatch(domain):
            invalid.append((number, raw))
            continue
        key = value.lower()
        if key in seen:
            duplicates.append((number, raw))
            continue
        seen.add(key)
        candidates.append((domain.lower(), is_suffix))

    if invalid or duplicates or len(candidates) != EXPECTED_ENTRIES:
        raise SystemExit(
            f"ERROR: source validation failed: entries={len(candidates)}, "
            f"invalid={len(invalid)}, duplicates={len(duplicates)}, "
            f"expected={EXPECTED_ENTRIES}"
        )
    if not CONFIG.is_file():
        raise SystemExit("ERROR: canonical shadowrocket/ss.conf is missing")

    # Read only existing domain rule types; other existing rule types are untouched.
    config_text = CONFIG.read_text(encoding="utf-8")
    if "[Rule]" not in config_text or "[Host]" not in config_text:
        raise SystemExit("ERROR: cannot isolate the canonical [Rule] section")
    rule_block = config_text.split("[Rule]", 1)[1].split("[Host]", 1)[0]
    existing = []
    for line_number, raw in enumerate(rule_block.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 3:
            continue
        kind = fields[0].upper()
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX"}:
            continue
        domain = fields[1].lower().lstrip(".")
        policy = fields[-1].upper()
        if DOMAIN_RE.fullmatch(domain):
            existing.append((kind, domain, policy, line_number))

    suffix_rules: dict[str, list[tuple[str, int]]] = {}
    exact_rules: dict[str, list[tuple[str, int]]] = {}
    for kind, domain, policy, line_number in existing:
        target = suffix_rules if kind == "DOMAIN-SUFFIX" else exact_rules
        target.setdefault(domain, []).append((policy, line_number))

    suffix_candidates: dict[str, list[int]] = {}
    for index, (domain, is_suffix) in enumerate(candidates):
        if is_suffix:
            suffix_candidates.setdefault(domain, []).append(index)

    hits: list[dict[str, set[str]]] = [dict() for _ in candidates]

    def record(index: int, policy: str, rule: str) -> None:
        hits[index].setdefault(policy, set()).add(rule)

    # Existing suffix rules that cover each candidate, plus exact matches.
    for index, (domain, _is_suffix) in enumerate(candidates):
        for parent in ancestors(domain):
            for policy, line_number in suffix_rules.get(parent, []):
                record(index, policy, f"DOMAIN-SUFFIX {parent} (rule line {line_number})")
        for policy, line_number in exact_rules.get(domain, []):
            record(index, policy, f"DOMAIN {domain} (rule line {line_number})")

    # Existing exact/suffix rules beneath a candidate suffix also overlap it.
    for kind, rule_domain, policy, line_number in existing:
        for parent in ancestors(rule_domain):
            for index in suffix_candidates.get(parent, []):
                record(index, policy, f"{kind} {rule_domain} (rule line {line_number})")

    by_policy = {"DIRECT": 0, "PROXY": 0, "REJECT": 0, "OTHER": 0}
    overlapping = 0
    conflicts = []
    for index, (domain, is_suffix) in enumerate(candidates):
        policies = hits[index]
        if not policies:
            continue
        overlapping += 1
        for policy in policies:
            by_policy[policy if policy in by_policy else "OTHER"] += 1
        if len(policies) > 1:
            conflicts.append((domain, is_suffix, policies))

    report = [
        "# External domain source audit",
        "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Source: {SOURCE_URL}",
        f"- Git blob SHA-1: `{actual_sha}`",
        f"- File bytes: {len(data)}",
        f"- Candidate entries: {len(candidates)} (expected {EXPECTED_ENTRIES})",
        f"- Exact entries: {sum(not suffix for _, suffix in candidates)}",
        f"- Subdomain entries: {sum(suffix for _, suffix in candidates)}",
        f"- Invalid entries: {len(invalid)}",
        f"- Duplicate entries: {len(duplicates)}",
        f"- Existing DOMAIN / DOMAIN-SUFFIX rules examined: {len(existing)}",
        f"- Candidate entries overlapping existing domain rules: {overlapping}",
        "",
        "## Existing policy overlap (candidate counts; categories can overlap)",
        "",
        "| Existing policy | Candidate entries overlapping |",
        "|---|---:|",
    ]
    for policy, count in by_policy.items():
        report.append(f"| {policy} | {count} |")
    report += [
        "",
        f"## Multi-policy collisions: {len(conflicts)}",
        "",
        "These candidates overlap existing rules carrying more than one policy. They must not be auto-classified.",
        "",
        "| Candidate | Source match | Existing policies |",
        "|---|---|---|",
    ]
    for domain, is_suffix, policies in conflicts:
        report.append(
            f"| `{domain}` | {'suffix' if is_suffix else 'exact'} | "
            f"{', '.join(sorted(policies))} |"
        )
    report += [
        "",
        "## Safety boundary",
        "",
        "- Only the pinned raw domain list was downloaded; no downloaded content was executed.",
        "- No upstream modules, scripts, MITM, DNS, rewrite, URL, IP, or policy directives are consumed.",
        "- No DIRECT / PROXY / REJECT policy is inferred or assigned.",
        "- No candidate domain is imported into the canonical config.",
        "- Existing config and DNS settings are read-only and remain unchanged.",
        "- Source hash changes stop the audit pending manual review.",
        "",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(report)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
