#!/usr/bin/env python3
"""Activate full rule-lifecycle review once 5,000 published rules have accumulated."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULESETS = ROOT / "rulesets"
STATE = RULESETS / "lifecycle_state.json"
POLICIES = ("direct", "proxy", "reject")
THRESHOLD = 5000


def count_published_rules(root: Path = ROOT) -> int:
    directory = root / "rulesets"
    expected = {name + ".list" for name in POLICIES}
    actual = {path.name for path in directory.glob("*.list")}
    if actual != expected:
        raise ValueError("published rulesets must contain exactly direct.list, proxy.list and reject.list")
    identities = set()
    for policy in POLICIES:
        path = directory / (policy + ".list")
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not (line.startswith("DOMAIN,") or line.startswith("DOMAIN-SUFFIX,")):
                raise ValueError(f"unsupported published rule in {path.name}: {line}")
            kind, domain = line.split(",", 1)
            if not domain or domain != domain.strip() or any(ch.isspace() for ch in domain):
                raise ValueError(f"malformed published rule in {path.name}: {line}")
            identities.add((policy.upper(), kind, domain.lower()))
    return len(identities)


def update_lifecycle_state(root: Path = ROOT, now: str | None = None) -> dict:
    directory = root / "rulesets"
    state_path = directory / "lifecycle_state.json"
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    count = count_published_rules(root)
    active = bool(previous.get("active")) or count >= THRESHOLD
    activated_at = previous.get("activated_at")
    if active and not activated_at:
        activated_at = now or datetime.now(timezone.utc).isoformat()
    state = {
        "schema_version": 1,
        "threshold": THRESHOLD,
        "count_basis": "unique_published_rules_across_DIRECT_PROXY_REJECT",
        "published_rule_count": count,
        "active": active,
        "status": "active" if active else "suspended_below_threshold",
        "activated_at": activated_at,
        "updated_at": now or datetime.now(timezone.utc).isoformat(),
        "semantics": "Activation is latched once the published total first reaches 5,000; it does not depend on additions, removals, or daily changes."
    }
    directory.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def main() -> None:
    state = update_lifecycle_state()
    print(json.dumps(state, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
