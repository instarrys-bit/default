#!/usr/bin/env python3
"""Join parser, policy and lineage evidence into a non-activating source candidate matrix."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENTS = ROOT / "sources/source_assessments.json"
LINEAGE = ROOT / "reports/source-lineage-audit.json"
OUTPUT = ROOT / "sources/source_candidates.json"
REPORT = ROOT / "reports/source-candidate-matrix.md"
SUPPORTED = {"domain-only", "adblock-domain-rules", "shadowrocket-domain-rules", "quantumult-domain-rules"}
POLICIES = ("DIRECT", "PROXY", "REJECT")

def build_matrix(assessments: dict, lineage: dict) -> dict:
    lineage_by_repo = {x["repository"]: x for x in lineage.get("candidate_sources", [])}
    shared_pairs = lineage.get("candidate_shared_reference_pairs", [])
    shared_by_repo = defaultdict(list)
    for pair in shared_pairs:
        left, right = pair["repositories"]
        shared_by_repo[left].append({"repository": right, "references": pair["shared_readme_references"]})
        shared_by_repo[right].append({"repository": left, "references": pair["shared_readme_references"]})
    grouped = {}
    for item in assessments.get("assessments", []):
        policy = item.get("policy_candidate")
        if policy not in POLICIES or item.get("parser_candidate") not in SUPPORTED:
            continue
        repo = item["repository"]
        key = (repo, policy)
        if key not in grouped:
            source_lineage = lineage_by_repo.get(repo, {})
            grouped[key] = {
                "repository": repo,
                "policy": policy,
                "files": [],
                "publisher_count_contribution": 1,
                "lineage_status": source_lineage.get("lineage_status", "unverified"),
                "lineage_audit_status": source_lineage.get("status", "not_audited"),
                "readme_reference_count": source_lineage.get("reference_count", 0),
                "readme_shared_reference_peers": shared_by_repo.get(repo, []),
                "archived": bool(item.get("archived", False)),
                "domain_fingerprints": set(),
            }
        grouped[key]["domain_fingerprints"].update(item.get("domain_fingerprints", []))
        grouped[key]["files"].append({
            "url": item["url"],
            "parser": item["parser_candidate"],
            "policy_evidence": item["policy_evidence"],
            "domain_count": item["exact_domain_count"] + item["suffix_domain_count"] + item["adblock_domain_count"] + item["domain_only_count"],
            "duplicate_domain_lines": item.get("duplicate_domain_lines", 0),
            "sha256": item.get("sha256"),
            "domain_fingerprint_count": len(item.get("domain_fingerprints", [])),
            "drift": item.get("drift", {}),
        })
    candidates = []
    for item in grouped.values():
        evidence = {x["policy_evidence"] for x in item["files"]}
        item["policy_evidence_types"] = sorted(evidence)
        item["policy_evidence_strong"] = bool(evidence & {"explicit_third_field", "README_RULE-SET_reference", "README_policy_reference"})
        item["total_domain_entries"] = sum(x["domain_count"] for x in item["files"])
        item["domain_fingerprint_count"] = len(item["domain_fingerprints"])
        item["domain_set_sha256"] = __import__("hashlib").sha256(
            "".join(sorted(item["domain_fingerprints"])).encode("ascii")
        ).hexdigest()
        item["file_count"] = len(item["files"])
        # Lineage and shared README references are provenance/correlation signals,
        # not blanket activation vetoes. Policy evidence, publisher status and
        # domain-level corroboration remain the actual gates.
        item["activation_eligible"] = (
            item["policy_evidence_strong"]
            and not item["archived"]
        )
        item["activation_blockers"] = []
        if not item["policy_evidence_strong"]:
            item["activation_blockers"].append("policy_evidence_not_strong")
        if item["archived"]:
            item["activation_blockers"].append("publisher_archived")
        item["lineage_warning"] = (
            "lineage_not_verified" if item["lineage_status"] != "verified" else None
        )
        if item["readme_shared_reference_peers"]:
            item["lineage_warning"] = "possible_shared_readme_references; correlation signal only"
        item["files"] = sorted(item["files"], key=lambda x: x["url"])
        candidates.append(item)
    candidates.sort(key=lambda x: (POLICIES.index(x["policy"]), -x["total_domain_entries"], x["repository"]))
    overlap_pairs = []
    for policy in POLICIES:
        group = [x for x in candidates if x["policy"] == policy]
        for i, left in enumerate(group):
            left_set = left["domain_fingerprints"]
            for right in group[i+1:]:
                right_set = right["domain_fingerprints"]
                shared = len(left_set & right_set)
                smaller = min(len(left_set), len(right_set))
                union = len(left_set | right_set)
                overlap = shared / smaller if smaller else 0.0
                jaccard = shared / union if union else 0.0
                relation = "near_duplicate" if overlap >= 0.95 else "high_overlap" if overlap >= 0.70 else "partial_overlap"
                overlap_pairs.append({
                    "policy": policy,
                    "repositories": [left["repository"], right["repository"]],
                    "shared_domain_count": shared,
                    "overlap_of_smaller": round(overlap, 4),
                    "jaccard": round(jaccard, 4),
                    "relation": relation,
                })
    cross_policy_conflicts = []
    for i, left_policy in enumerate(POLICIES):
        left = set().union(*(x["domain_fingerprints"] for x in candidates if x["policy"] == left_policy)) if any(x["policy"] == left_policy for x in candidates) else set()
        for right_policy in POLICIES[i+1:]:
            right = set().union(*(x["domain_fingerprints"] for x in candidates if x["policy"] == right_policy)) if any(x["policy"] == right_policy for x in candidates) else set()
            shared = len(left & right)
            if shared:
                cross_policy_conflicts.append({"policies": [left_policy, right_policy], "shared_domain_count": shared})
    by_policy = {}
    for policy in POLICIES:
        group = [x for x in candidates if x["policy"] == policy]
        eligible = [x for x in group if x["activation_eligible"]]
        parent = {x["repository"]: x["repository"] for x in eligible}
        def find(value):
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value
        for pair in overlap_pairs:
            if pair["policy"] == policy and pair["relation"] in {"near_duplicate", "high_overlap"}:
                left, right = pair["repositories"]
                if left in parent and right in parent:
                    parent[find(left)] = find(right)
        independent_groups = len({find(x["repository"]) for x in eligible}) if eligible else 0
        by_policy[policy] = {
            "candidate_publishers": len({x["repository"] for x in group}),
            "eligible_publishers": len({x["repository"] for x in eligible}),
            "independent_eligible_groups": independent_groups,
            "candidate_files": sum(x["file_count"] for x in group),
            "cross_policy_conflict_count": sum(1 for x in cross_policy_conflicts if policy in x["policies"]),
            "activation_ready": independent_groups >= 2,
        }
    for item in candidates:
        item.pop("domain_fingerprints", None)
    return {
        "schema_version": 1,
        "candidate_count": len(candidates),
        "activation_count": sum(1 for x in candidates if x["activation_eligible"]),
        "minimum_independent_publishers": 2,
        "policy_summary": by_policy,
        "same_policy_domain_overlap": overlap_pairs,
        "cross_policy_conflicts": cross_policy_conflicts,
        "candidates": candidates,
        "activation_policy": "This matrix never edits the active source registry. Two independent policy-evidenced publishers per policy remain mandatory; incomplete lineage and shared README references are recorded as warnings, not blanket vetoes.",
    }

def render_report(data: dict) -> str:
    rows = [
        "# Automated source candidate matrix",
        "",
        "This report combines parser compatibility, explicit policy evidence and README reference overlap. It does not activate sources.",
        "",
        "| Policy | Candidate publishers | Verified publishers | Candidate files | Ready |",
        "|---|---:|---:|---:|---|",
    ]
    for policy, summary in data["policy_summary"].items():
        rows.append(f"| {policy} | {summary['candidate_publishers']} | {summary['eligible_publishers']} | {summary['candidate_files']} | {'yes' if summary['activation_ready'] else 'no'} |")
    rows.extend(["", "## Same-policy source overlap", ""])
    if data.get("same_policy_domain_overlap"):
        for pair in data["same_policy_domain_overlap"]:
            rows.append(
                f"- {pair['policy']}: {pair['repositories'][0]} ↔ {pair['repositories'][1]} — "
                f"{pair['shared_domain_count']} shared domains; {pair['overlap_of_smaller']:.1%} of smaller set; "
                f"{pair['relation']}"
            )
    else:
        rows.append("- No same-policy source pairs to compare.")
    rows.extend(["", "## Cross-policy overlap", ""])
    if data.get("cross_policy_conflicts"):
        for conflict in data["cross_policy_conflicts"]:
            rows.append(f"- {' / '.join(conflict['policies'])}: {conflict['shared_domain_count']} shared domain fingerprints; held for conflict review.")
    else:
        rows.append("- No cross-policy overlap detected.")
    rows.extend(["", "## Candidate publishers", ""])
    for item in data["candidates"]:
        rows.extend([
            f"### {item['policy']} — {item['repository']}",
            "",
            f"- Domain entries across candidate files: {item['total_domain_entries']}",
            f"- Policy evidence: {', '.join(item['policy_evidence_types'])}",
            f"- Lineage: {item['lineage_status']} ({item['lineage_audit_status']})",
            f"- Possible shared README-reference peers: {', '.join(x['repository'] for x in item['readme_shared_reference_peers']) or 'none found'}",
            f"- Activation eligible: {item['activation_eligible']}",
            f"- Blockers: {', '.join(item['activation_blockers']) or 'none'}",
            "",
        ])
        for file in item["files"]:
            rows.append(f"  - {file['parser']}: {file['url']} ({file['domain_count']} domain entries)")
        rows.append("")
    rows.extend([
        "## Safety rule",
        "",
        "Publisher count is repository-level, not file-level: several files from one repository count as one publisher. Domain overlap uses salted-free truncated SHA-256 fingerprints, not raw domain names. Near-identical source sets are grouped as one possible publisher lineage; high overlap is a correlation warning, not proof of common ancestry. README hyperlinks are only possible shared-reference signals. No candidate is activated without verified lineage and strong policy evidence.",
        "",
    ])
    return "\n".join(rows)

def main() -> int:
    assessments = json.loads(ASSESSMENTS.read_text(encoding="utf-8"))
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))
    result = build_matrix(assessments, lineage)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "candidate_publishers": result["candidate_count"],
        "activation_count": result["activation_count"],
        "by_policy": result["policy_summary"],
    }, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
