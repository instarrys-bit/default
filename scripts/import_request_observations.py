#!/usr/bin/env python3
"""Merge observed request hostnames into the candidate buffer without assigning policy."""
from __future__ import annotations

import json, os, re
from pathlib import Path
from json_document_store import read_document, write_document

ROOT = Path(__file__).resolve().parents[1]
BUFFER = ROOT / "data/domain_candidates.json"
MAX_CANDIDATE_RECORDS = 30_000_000
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def main() -> None:
    raw = os.environ.get("REQUEST_OBSERVATIONS_JSON", "").strip()
    if not raw:
        print("No request observations supplied; nothing to import.")
        return
    domains = json.loads(raw)
    if not isinstance(domains, list) or len(domains) > 500 or any(not isinstance(x, str) for x in domains):
        raise ValueError("request observations must be a JSON array of at most 500 hostnames")
    incoming = [{"domain": value, "first_seen": None, "observations": 1} for value in domains]
    buffer = read_document(BUFFER, "candidates", {"schema_version": 2, "candidates": [], "bootstrapped_sources": []})
    queue = {str(x["domain"]).lower(): x for x in buffer.get("candidates", [])}
    added = 0
    for item in incoming:
        domain = str(item.get("domain", "")).lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("invalid observed hostname: " + domain)
        if domain not in queue:
            queue[domain] = {
                "domain": domain,
                "source_id": "request-intake-observation",
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
