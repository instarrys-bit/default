#!/usr/bin/env python3
"""Merge observed request hostnames into the candidate buffer without assigning policy."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "sources/request_domain_observations.json"
BUFFER = ROOT / "data/domain_candidates.json"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def main() -> None:
    if not OBSERVATIONS.exists():
        print("No request observation file; nothing to import.")
        return
    incoming = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    if incoming.get("schema_version") != 1 or not isinstance(incoming.get("observations"), list):
        raise ValueError("unsupported request observation schema")
    buffer = json.loads(BUFFER.read_text(encoding="utf-8")) if BUFFER.exists() else {"schema_version": 2, "candidates": [], "bootstrapped_sources": []}
    queue = {str(x["domain"]).lower(): x for x in buffer.get("candidates", [])}
    added = 0
    for item in incoming["observations"]:
        domain = str(item.get("domain", "")).lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("invalid observed hostname: " + domain)
        if domain not in queue:
            queue[domain] = {
                "domain": domain,
                "source_id": "youtube-request-observation",
                "first_seen": item.get("first_seen"),
                "classification": "REVIEW",
                "observation_count": int(item.get("observations", 1))
            }
            added += 1
    buffer["schema_version"] = 2
    buffer["candidates"] = sorted(queue.values(), key=lambda x: x["domain"])
    BUFFER.parent.mkdir(parents=True, exist_ok=True)
    BUFFER.write_text(json.dumps(buffer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {added} new observed hostnames; no routing policy assigned.")

if __name__ == "__main__":
    main()
