#!/usr/bin/env python3
"""Build exact-domain RULE-SET lists only from deterministic evidence-approved records."""
from __future__ import annotations
import json, re
from pathlib import Path
from deterministic_review import inspect
from domain_rule_engine import RuleIndex, load_domain_rules
from source_registry import validate_registry

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"sources/domain_reviews.json"
SOURCE_FILE=ROOT/"sources/domain_sources.json"
CURRENT_SNAPSHOT=ROOT/"data/candidates.json"
CONFIG=ROOT/"sources/baseline/ss.conf"
PROTECTED=ROOT/"sources/protected_domains.json"
OUT=ROOT/"rulesets"
POLICIES={"DIRECT","PROXY","REJECT"}
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def main():
    data=json.loads(LEDGER.read_text(encoding="utf-8"))
    source_cfg=json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    source_map=validate_registry(source_cfg)
    scoring=source_cfg.get("scoring",{})
    required_by_policy=scoring.get("required_sources_by_policy",{})
    minimum=int(scoring.get("minimum_independent_sources",2))
    threshold=float(scoring.get("minimum_confidence",0.8))
    current=json.loads(CURRENT_SNAPSHOT.read_text(encoding="utf-8"))
    current_hashes={x["id"]:x["sha256"] for x in current.get("sources",[])}
    enabled_source_ids={sid for sid,source in source_map.items() if source.get("enabled",True) is not False}
    if set(current_hashes)!=enabled_source_ids:
        raise ValueError("current source snapshot does not match enabled source registry entries")
    protected=json.loads(PROTECTED.read_text(encoding="utf-8"))
    base=CONFIG.read_text(encoding="utf-8")
    rules,conditional,_=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    rule_sets={policy:set() for policy in POLICIES}
    seen={}
    status_counts={}
    held=approved=0
    reviews=data.get("reviews",[])
    if len({str(item.get("domain","")).lower() for item in reviews})!=len(reviews):
        raise ValueError("duplicate domain key in deterministic ledger")

    for item in reviews:
        status=str(item.get("status","UNKNOWN"))
        status_counts[status]=status_counts.get(status,0)+1
        if status!="APPROVED":
            held+=1
            continue
        domain=str(item.get("domain","")).lower().rstrip(".")
        policy=str(item.get("policy","")).upper()
        if not DOMAIN_RE.fullmatch(domain) or policy not in POLICIES:
            raise ValueError("invalid approved domain or policy: "+domain)
        if item.get("decision_engine")!="deterministic-domain-audit/3.0":
            raise ValueError("approved record was not produced by the current deterministic reviewer: "+domain)
        if domain in seen:
            raise ValueError("duplicate or cross-policy approved domain: "+domain)
        valid=[]
        for ev in item.get("evidence",[]):
            sid=str(ev.get("source_id",""))
            src=source_map.get(sid)
            if not src or ev.get("currently_listed",True) is not True:
                continue
            if ev.get("sha256")!=current_hashes.get(sid):
                continue
            if str(src.get("classification","")).upper()!=policy:
                continue
            if str(ev.get("classification","")).upper()!=policy:
                continue
            if ev.get("publisher")!=src.get("publisher"):
                continue
            if ev.get("independence_group")!=src.get("independence_group"):
                continue
            if ev.get("url")!=src.get("url"):
                continue
            if ev.get("lineage_status") not in {"verified","partial","unverified"} or ev.get("lineage_status")!=src.get("lineage_status"):
                continue
            if src.get("policy_evidence") is not None and ev.get("policy_evidence")!=src.get("policy_evidence"):
                continue
            if ev.get("upstream_repositories")!=src.get("upstream_repositories",[]):
                continue
            valid.append(ev)
        source_ids={str(ev["source_id"]) for ev in valid}
        publishers={str(ev["publisher"]) for ev in valid if ev.get("publisher")}
        groups={str(ev["independence_group"]) for ev in valid if ev.get("independence_group")}
        required=set(required_by_policy.get(policy,[]))
        confidence=float(item.get("confidence",0))
        if (not required.issubset(source_ids) or len(source_ids)<minimum
            or len(publishers)<minimum or len(groups)<minimum or confidence<threshold):
            raise ValueError("approved record no longer meets current evidence gate: "+domain)
        if int(item.get("source_count",0))<minimum:
            raise ValueError("approved record source count below minimum: "+domain)
        if any(item.get(key)!="PASS" for key in ("duplicate_check","conflict_check","risk_check")):
            raise ValueError("approved record failed a local safety gate: "+domain)
        local_status,reason=inspect(domain,index,conditional,base,protected,policy)
        if local_status:
            raise ValueError("approved record now overlaps baseline ("+str(local_status)+"): "+domain+" / "+str(reason))
        seen[domain]=policy
        rule_sets[policy].add(domain)
        approved+=1

    OUT.mkdir(parents=True,exist_ok=True)
    for policy in sorted(POLICIES):
        lines=["DOMAIN,"+domain for domain in sorted(rule_sets[policy])]
        (OUT/(policy.lower()+".list")).write_text("\n".join(lines)+("\n" if lines else ""),encoding="utf-8")
    candidate_matrix_path=ROOT/"sources/source_candidates.json"
    candidate_matrix=json.loads(candidate_matrix_path.read_text(encoding="utf-8")) if candidate_matrix_path.exists() else {}
    manifest={
        "schema_version":2,
        "source_ledger":"sources/domain_reviews.json",
        "current_source_snapshot":"data/candidates.json",
        "artifact_scope":"standalone_rulesets_only",
        "outputs":["direct.list","proxy.list","reject.list"],
        "review_engine":"deterministic-domain-audit/3.0",
        "minimum_independent_sources":minimum,
        "minimum_confidence_score":threshold,
        "required_sources_by_policy":required_by_policy,
        "source_inventory":current.get("sources",[]),
        "source_count":len(current.get("sources",[])),
        "policy_conflict_total":status_counts.get("POLICY_CONFLICT",0),
        "lineage_verified_sources":sum(1 for x in current.get("sources",[]) if x.get("lineage_status")=="verified"),
        "lineage_unverified_sources":sum(1 for x in current.get("sources",[]) if x.get("lineage_status")=="unverified"),
        "lineage_partial_sources":sum(1 for x in current.get("sources",[]) if x.get("lineage_status")=="partial"),
        "lineage_not_fully_verified_sources":sum(1 for x in current.get("sources",[]) if x.get("lineage_status")!="verified"),
        "source_candidate_summary": candidate_matrix.get("policy_summary", {}) if candidate_matrix else {},
        "rule_count":{policy:len(rule_sets[policy]) for policy in sorted(POLICIES)},
        "reviewed_total":len(reviews),
        "approved_total":approved,
        "held_total":held,
        "status_count":dict(sorted(status_counts.items())),
        "deterministic_review_progress":{
            "candidate_total":len(reviews),
            "approved_total":approved,
            "held_total":held,
            "status_count":dict(sorted(status_counts.items()))
        },
        "format":"Standalone Shadowrocket RULE-SET lists: DOMAIN,<domain>; policy is assigned by the RULE-SET reference.",
        "import_instruction":"Optionally reference each published raw list URL in the user-managed Shadowrocket [Rule] section with RULE-SET,<raw URL>,<matching policy>. This automation does not edit the user config.",
        "limitations":[
            "Only exact DOMAIN candidates with current policy-labelled evidence and all local gates passing are published.",
            "A domain is published only when at least two distinct configured publishers and source groups agree on its routing policy; a single-source candidate remains under review.",
            "Lineage status is retained as provenance metadata, not a blanket publication veto; source overlap is a correlation signal, not proof of identical domain ancestry.",
            "Broad single-label suffixes are excluded; only exact-domain entries are emitted.",
            "Static checks do not replace Shadowrocket device testing."
        ]
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
