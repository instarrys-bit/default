"""Pure metrics for the read-only operations dashboard."""
from __future__ import annotations


def build_candidate_review_metrics(candidates, review_records, cursor=None, ledger_updated_at=None):
    candidate_domains = {
        str(item.get("domain", "")).lower().rstrip(".")
        for item in candidates
        if isinstance(item, dict) and item.get("domain")
    }
    review_by_domain = {
        str(item.get("domain", "")).lower().rstrip("."): item
        for item in review_records
        if isinstance(item, dict) and item.get("domain")
    }
    status_counts = {}
    for domain in candidate_domains:
        record = review_by_domain.get(domain)
        status = str(record.get("status", "UNKNOWN")).upper() if record else "UNREVIEWED"
        status_counts[status] = status_counts.get(status, 0) + 1
    cursor = cursor if isinstance(cursor, dict) else {}
    recorded = sum(1 for domain in candidate_domains if domain in review_by_domain)
    return {
        "candidate_total": len(candidate_domains),
        "history_recorded": recorded,
        "missing_history": len(candidate_domains) - recorded,
        "status_counts": status_counts,
        "review_ledger_total": len(review_records),
        "review_ledger_updated_at": ledger_updated_at,
        "cursor_status": str(cursor.get("status", "unknown")),
        "cursor_candidate_count": cursor.get("candidate_count", 0)
        if isinstance(cursor.get("candidate_count", 0), int) else 0,
    }
