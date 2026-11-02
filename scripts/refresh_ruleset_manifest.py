#!/usr/bin/env python3
"""Reconcile generated RULE-SET manifest counts with the final published lists."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("DIRECT", "PROXY", "REJECT")
OUTPUTS = {policy.lower() + ".list" for policy in POLICIES}
DOMAIN_LINE = re.compile(
    r"^(DOMAIN|DOMAIN-SUFFIX),"
    r"(?=.{1,253}$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$",
    re.IGNORECASE,
)
MAX_PUBLISHED_RULES = 30_000


def _read_rules(path: Path) -> tuple[list[str], str]:
    raw = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    parsed = [DOMAIN_LINE.fullmatch(line) for line in lines]
    if any(match is None for match in parsed):
        raise ValueError(f"{path.name} contains an unsupported or malformed rule")
    normalized = [(match.group(1).upper(), match.group(0).split(",", 1)[1].lower()) for match in parsed]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{path.name} contains duplicate domain scopes")
    canonical = "\n".join(lines) + ("\n" if lines else "")
    return lines, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def refresh(root: Path = ROOT) -> dict:
    root = Path(root)
    rules_dir = root / "rulesets"
    manifest_path = rules_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("rulesets/manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("ruleset manifest must be a JSON object")
    declared = {str(item).lower() for item in manifest.get("outputs", [])}
    if declared != OUTPUTS:
        raise ValueError("manifest outputs do not match the three managed RULE-SET files")
    actual = {path.name for path in rules_dir.glob("*.list")}
    if actual != OUTPUTS:
        raise ValueError("ruleset directory must contain exactly direct.list, proxy.list and reject.list")

    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for policy in POLICIES:
        lines, digest = _read_rules(rules_dir / (policy.lower() + ".list"))
        counts[policy] = len(lines)
        hashes[policy] = digest

    total = sum(counts.values())
    if total > MAX_PUBLISHED_RULES:
        raise ValueError(
            f"published rules exceed the combined {MAX_PUBLISHED_RULES:,}-rule cap: {total:,}"
        )
    manifest["rule_count"] = counts
    manifest["published_rule_total"] = total
    lifecycle = manifest.setdefault("rule_lifecycle", {})
    if not isinstance(lifecycle, dict):
        raise ValueError("manifest rule_lifecycle must be an object")
    for policy in POLICIES:
        entry = lifecycle.setdefault(policy, {})
        if not isinstance(entry, dict):
            raise ValueError(f"manifest lifecycle entry for {policy} must be an object")
        entry["current_count"] = counts[policy]
        entry["current_sha256"] = hashes[policy]

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"rule_count": counts, "published_rule_total": total, "sha256": hashes}


def main() -> int:
    result = refresh()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
