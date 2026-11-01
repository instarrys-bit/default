#!/usr/bin/env python3
"""Schedule lifecycle reviews every 5,000 published additions and monthly at capacity."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULESETS = ROOT / "rulesets"
STATE = RULESETS / "lifecycle_state.json"
POLICIES = ("direct", "proxy", "reject")
MILESTONE = 5000
MAX_PUBLISHED = 30000
MONTH_DAYS = 30


def count_published_rules(root: Path = ROOT) -> int:
    directory = root / "rulesets"
    expected = {name + ".list" for name in POLICIES}
    if {path.name for path in directory.glob("*.list")} != expected:
        raise ValueError("published rulesets must contain exactly direct.list, proxy.list and reject.list")
    identities = set()
    for policy in POLICIES:
        for raw in (directory / (policy + ".list")).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not (line.startswith("DOMAIN,") or line.startswith("DOMAIN-SUFFIX,")):
                raise ValueError(f"unsupported published rule in {policy}.list: {line}")
            kind, domain = line.split(",", 1)
            domain = domain.lower()
            if not domain or domain != domain.strip() or any(ch.isspace() for ch in domain):
                raise ValueError(f"malformed published rule in {policy}.list: {line}")
            identities.add((policy.upper(), kind, domain))
    return len(identities)


def update_lifecycle_state(root: Path = ROOT, now: str | None = None) -> dict:
    directory = root / "rulesets"
    state_path = directory / "lifecycle_state.json"
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    timestamp = now or datetime.now(timezone.utc).isoformat()
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    count = count_published_rules(root)
    high_water = max(int(previous.get("published_high_water_mark", previous.get("published_rule_count", 0))), count)
    next_milestone = int(previous.get("next_milestone", MILESTONE))
    due_milestones = []
    while high_water >= next_milestone:
        due_milestones.append(next_milestone)
        next_milestone += MILESTONE
    last_monthly = previous.get("last_monthly_review_at")
    monthly_due = False
    if count >= MAX_PUBLISHED:
        if not last_monthly:
            monthly_due = True
        else:
            last = datetime.fromisoformat(str(last_monthly).replace("Z", "+00:00"))
            monthly_due = moment - last >= timedelta(days=MONTH_DAYS)
    state = {
        "schema_version": 2,
        "milestone_interval": MILESTONE,
        "max_published_rules": MAX_PUBLISHED,
        "count_basis": "unique_published_rules_across_DIRECT_PROXY_REJECT",
        "published_rule_count": count,
        "published_high_water_mark": high_water,
        "next_milestone": next_milestone,
        "due_milestones": due_milestones,
        "monthly_review_interval_days": MONTH_DAYS,
        "monthly_review_due": monthly_due,
        "queue_mode": count >= MAX_PUBLISHED,
        "status": "capacity_monthly_review_due" if monthly_due else ("milestone_review_due" if due_milestones else ("capacity_queue_only" if count >= MAX_PUBLISHED else "normal_incremental")),
        "last_successful_review_at": previous.get("last_successful_review_at"),
        "last_monthly_review_at": last_monthly,
        "updated_at": timestamp,
        "deletion_policy": "Only separately verified lifecycle-invalid decisions may remove rules. Evidence loss, source disappearance, lineage changes, conflicts or missing observations are not deletion evidence."
    }
    directory.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def main() -> None:
    print(json.dumps(update_lifecycle_state(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
