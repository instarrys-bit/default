#!/usr/bin/env python3
"""Build standalone Shadowrocket rule-set files; never edit any config."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "sources" / "domain_reviews.json"
OUT = ROOT / "rulesets"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
POLICIES = {"DIRECT", "PROXY", "REJECT"}

def main() -> None:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    rules = {policy: set() for policy in POLICIES}
    held = 0
    for item in payload.get("reviews", []):
        if item.get("status") != "APPROVED":
            held += 1
            continue
        domain = str(item.get("domain", "")).lower().rstrip(".")
        policy = str(item.get("policy", "")).upper()
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError(f"invalid approved domain: {domain!r}")
        if policy not in POLICIES:
            raise ValueError(f"unsupported policy for {domain}: {policy!r}")
        rules[policy].add(domain)

    OUT.mkdir(parents=True, exist_ok=True)
    for policy in sorted(POLICIES):
        path = OUT / f"{policy.lower()}.list"
        lines = [f"DOMAIN,{domain},{policy}" for domain in sorted(rules[policy])]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "source_ledger": "sources/domain_reviews.json",
        "baseline": "sources/baseline/ss.conf",
        "config_modified": False,
        "rule_count": {policy: len(rules[policy]) for policy in sorted(POLICIES)},
        "held_or_not_approved": held,
        "format": "Shadowrocket DOMAIN,<domain>,<policy>",
        "import_instruction": "User manually adds the selected rule-set URL/reference to their config after reviewing it."
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
