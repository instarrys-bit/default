#!/usr/bin/env python3
"""Pure helpers for resumable, snapshot-bound deterministic review progress."""
from __future__ import annotations
import hashlib, json

def snapshot_digest(sources, candidates):
    payload={"sources":sources,"candidates":candidates}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()

def resume_index(cursor, digest, candidate_count):
    if cursor.get("snapshot_sha256") != digest or cursor.get("status") != "in_progress":
        return 0
    try: index=int(cursor.get("next_index",0))
    except (TypeError,ValueError): return 0
    return max(0,min(index,candidate_count))

def checkpoint(digest, candidate_count, next_index, batch_size, status="in_progress"):
    if status not in {"in_progress","complete"}: raise ValueError("invalid cursor status")
    if not 0 <= next_index <= candidate_count or batch_size < 1: raise ValueError("invalid cursor bounds")
    if status=="complete" and next_index != candidate_count: raise ValueError("completed cursor must cover every candidate")
    return {"schema_version":1,"snapshot_sha256":digest,"candidate_count":candidate_count,"next_index":next_index,"batch_size":batch_size,"status":status}
