#!/usr/bin/env python3
"""Merge observed request hostnames into the candidate buffer without assigning policy."""
from __future__ import annotations

import json, re
from pathlib import Path
from json_document_store import read_document, write_document
from production_intent import load_request_observation_ledger

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "sources/request_domain_observations.json"
BUFFER = ROOT / "data/domain_candidates.json"
MAX_CANDIDATE_RECORDS = 30_000_000
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def main() -> None:
    if OBSERVATIONS.exists():
        seed = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    else:
        seed = {"schema_version": 1, "observations": []}
    incoming = load_request_observation_ledger(ROOT, seed)
    if not incoming.get("observations"):
        print("No request observation batches; nothing to import.")
        return
    buffer = read_document(BUFFER, "candidates", {"schema_version": 2, "candidates": [], "bootstrapped_sources": []})
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
    if len(queue) > MAX_CANDIDATE_RECORDS:
        raise ValueError(f"candidate retention exceeds hard limit: {len(queue):,} > {MAX_CANDIDATE_RECORDS:,}")
    buffer["candidates"] = sorted(queue.values(), key=lambda x: x["domain"])
    BUFFER.parent.mkdir(parents=True, exist_ok=True)
    write_document(BUFFER, buffer, "candidates")
    print(f"Imported {added} new observed hostnames; no routing policy assigned.")

if __name__ == "__main__":
    main()
