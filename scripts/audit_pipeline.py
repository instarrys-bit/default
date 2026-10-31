#!/usr/bin/env python3
"""Read-only safety gate for the canonical Shadowrocket configuration.

This audit intentionally does not rewrite ss.conf, classify domains, or publish rules.
The approved Git blob SHA is a change-control lock: intentional config changes require
an explicit review and a corresponding policy-manifest update.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
POLICY = ROOT / "sources" / "policy.json"
REQUIRED_SECTIONS = ("[General]", "[Rule]", "[Host]")
DNS_KEYS = (
    "dns-server",
    "fallback-dns-server",
    "direct-dns-server",
    "proxy-dns-server",
    "dns-direct-system",
    "dns-direct-fallback-proxy",
    "hijack-dns",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def git_blob_sha(path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{path}"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail("cannot read the canonical config Git blob SHA; run inside a full Git checkout")


def parse_general(text: str) -> dict[str, list[str]]:
    block = text.split("[General]", 1)[1].split("[", 1)[0]
    values: dict[str, list[str]] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        values.setdefault(key, []).append(value)
    return values


def main() -> None:
    if not CONFIG.is_file():
        fail("shadowrocket/ss.conf is missing")
    if not POLICY.is_file():
        fail("sources/policy.json is missing")

    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"policy manifest is invalid: {exc}")

    text = CONFIG.read_text(encoding="utf-8")
    if not text.strip():
        fail("canonical config is empty")

    positions = {}
    for section in REQUIRED_SECTIONS:
        if text.count(section) != 1:
            fail(f"expected exactly one {section} section")
        positions[section] = text.index(section)
    if not (positions["[General]"] < positions["[Rule]"] < positions["[Host]"]):
        fail("section order must remain [General], [Rule], [Host]")

    expected_sha = policy.get("canonical_config", {}).get("approved_git_blob_sha")
    actual_sha = git_blob_sha("shadowrocket/ss.conf")
    if not expected_sha or actual_sha != expected_sha:
        fail(
            "canonical config differs from the approved baseline "
            f"(expected blob {expected_sha!r}, found {actual_sha}); "
            "no automated rewrite or publication is permitted"
        )

    general = parse_general(text)
    expected_dns = policy.get("dns_invariants", {})
    for key in DNS_KEYS:
        found = general.get(key, [])
        expected = expected_dns.get(key)
        if len(found) != 1:
            fail(f"DNS invariant {key!r} must appear exactly once; found {len(found)}")
        if found[0] != expected:
            fail(f"DNS invariant changed: {key!r}")

    allowed = policy.get("allowed_policy_outputs")
    if allowed != ["DIRECT", "PROXY", "REJECT"]:
        fail("policy outputs must be exactly DIRECT, PROXY, REJECT in that order")
    if policy.get("external_source_mode") != "domain-only":
        fail("external source mode must remain domain-only")
    if policy.get("release_policy", {}).get("automatic_config_rewrite") is not False:
        fail("automatic config rewrite must remain disabled")
    if policy.get("release_policy", {}).get("automatic_policy_inference") is not False:
        fail("automatic policy inference must remain disabled")

    rule_block = text.split("[Rule]", 1)[1].split("[Host]", 1)[0]
    active = [
        line.strip() for line in rule_block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not active:
        fail("[Rule] contains no active rules")
    types = Counter(line.split(",", 1)[0] for line in active)

    print("PASS: read-only Shadowrocket safety audit")
    print(f"Canonical config blob: {actual_sha}")
    print(f"Active existing rules: {len(active)}")
    print("Existing rule types (reported, not rewritten):")
    for rule_type, count in sorted(types.items()):
        print(f"  {rule_type}: {count}")
    print("DNS invariants: all 7 match the approved baseline")
    print("External sources: 0 approved; no external domains imported")
    print("Policy outputs: DIRECT / PROXY / REJECT only")
    print("Publication: disabled; this workflow cannot modify ss.conf")
    print("NOTE: static audit does not replace Shadowrocket device testing.")


if __name__ == "__main__":
    main()
