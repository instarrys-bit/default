#!/usr/bin/env python3
"""Build exact-domain RULE-SET lists only from deterministic evidence-approved records."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()

import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from deterministic_review import inspect, parse_skip_proxy, evidence_gate, load_correlated_publishers
from domain_rule_engine import RuleIndex, load_domain_rules, inspect_suffix_scope
from audit_ruleset_config_overlap import all_rule_lines, prepare_rules
from sync_ruleset_config_conflicts import classify_rule
from source_registry import validate_registry

from json_document_store import read_document
ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"sources/domain_reviews.json"
SOURCE_FILE=ROOT/"sources/domain_sources.json"
CURRENT_SNAPSHOT=ROOT/"data/candidates.json"
CONFIG=ROOT/"shadowrocket/ss.conf"
PROTECTED=ROOT/"sources/protected_domains.json"
OUT=ROOT/"rulesets"
LIFECYCLE_STATE=OUT/"lifecycle_state.json"
REJECT_APPROVALS=ROOT/"sources/reject_manual_approvals.json"
POLICIES={"DIRECT","PROXY","REJECT"}
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")


def load_reject_approvals(path=REJECT_APPROVALS):
    if not path.exists():
        return set()
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict) or payload.get("schema_version")!=1:
        raise ValueError("reject manual-approval ledger has an unsupported schema")
    entries=payload.get("approved_rules",[])
    if not isinstance(entries,list):
        raise ValueError("reject manual-approval ledger approved_rules must be a list")
    approved=set()
    for line in entries:
        if not isinstance(line,str) or not re.fullmatch(r"DOMAIN(?:-SUFFIX)?,[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",line,re.IGNORECASE):
            raise ValueError("invalid manually approved REJECT rule: "+str(line))
        normalized=line.split(",",1)[0].upper()+","+line.split(",",1)[1].lower().rstrip(".")
        if normalized in approved:
            raise ValueError("duplicate manually approved REJECT rule: "+normalized)
        approved.add(normalized)
    return approved


def reject_rule_authorized(line, previously_published, manual_approvals):
    return line in previously_published or line in manual_approvals

def previously_published_reject_rules(previously_published, config_archive):
    """Preserve prior publication authorization after a config conflict is removed."""
    authorized = set(previously_published)
    for item in config_archive.get("items", []):
        if (
            str(item.get("policy", "")).upper() == "REJECT"
            and item.get("origin") == "published_ruleset"
            and item.get("superseded_at")
            and not item.get("restored_at")
        ):
            line = item.get("rule")
            if isinstance(line, str) and line:
                authorized.add(line)
    return authorized



def promote_queue_to_capacity(rule_sets, queue_map, previous_rule_count, maximum=30000):
    if previous_rule_count < 0 or previous_rule_count > maximum:
        raise ValueError("published count is outside the configured capacity")
    capacity = maximum - previous_rule_count
    promoted = []
    ordered = sorted(
        queue_map,
        key=lambda x: (
            int(queue_map[x].get("priority", 1)),
            str(queue_map[x].get("queued_at", "")),
            x[0], x[2], x[1]
        )
    )
    for key in ordered:
        policy, scope, domain = key
        if policy not in POLICIES or scope not in {"exact_candidate", "suffix_candidate"}:
            raise ValueError("invalid pending queue identity")
        if (scope, domain) in rule_sets[policy]:
            promoted.append(key)
            continue
        if capacity <= 0:
            break
        rule_sets[policy].add((scope, domain))
        promoted.append(key)
        capacity -= 1
    for key in promoted:
        queue_map.pop(key, None)
    return promoted

def main():
    data=read_document(LEDGER,"reviews",{"reviews":[]})
    source_cfg=json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    source_map=validate_registry(source_cfg)
    correlated_pairs=load_correlated_publishers()
    scoring=source_cfg.get("scoring",{})
    required_by_policy=scoring.get("required_sources_by_policy",{})
    minimum=int(scoring.get("minimum_independent_sources",2))
    threshold=float(scoring.get("minimum_confidence",0.8))
    current=read_document(CURRENT_SNAPSHOT,"candidates",{"candidates":[]})
    current_hashes={x["id"]:x["sha256"] for x in current.get("sources",[])}
    enabled_source_ids={sid for sid,source in source_map.items() if source.get("enabled",True) is not False}
    if set(current_hashes)!=enabled_source_ids:
        raise ValueError("current source snapshot does not match enabled source registry entries")
    protected=json.loads(PROTECTED.read_text(encoding="utf-8"))
    base=CONFIG.read_text(encoding="utf-8")
    config_rules=all_rule_lines(base)
    prepared_config_rules=prepare_rules(config_rules)
    config_skip_proxy=parse_skip_proxy(base)
    rules,conditional,_=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    lifecycle_state=json.loads(LIFECYCLE_STATE.read_text(encoding="utf-8")) if LIFECYCLE_STATE.exists() else {}
    lifecycle_active=bool(lifecycle_state.get("active"))
    archive_path=OUT/"deletion_archive.json"
    deletion_archive=json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {"items":[]}
    archived_deleted={(str(x.get("policy","")).upper(),str(x.get("rule",""))) for x in deletion_archive.get("items",[]) if not x.get("restored_at")}
    config_archive_path=OUT/"config_conflict_archive.json"
    config_archive=json.loads(config_archive_path.read_text(encoding="utf-8")) if config_archive_path.exists() else {"items":[]}
    config_conflict_archived={(str(x.get("policy","")).upper(),str(x.get("rule",""))) for x in config_archive.get("items",[]) if not x.get("restored_at") and not x.get("superseded_at")}
    archived_deleted |= config_conflict_archived
    manual_reject_approvals=load_reject_approvals()
    previous_published={policy:set() for policy in POLICIES}
    for policy in POLICIES:
        previous_path=OUT/(policy.lower()+".list")
        if previous_path.exists():
            previous_published[policy]=set(x.strip() for x in previous_path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.strip().startswith("#") and (policy.upper(),x.strip()) not in archived_deleted)
    previously_published_reject = previously_published_reject_rules(
        previous_published["REJECT"], config_archive
    )
    rule_sets={policy:set() for policy in POLICIES}
    new_approved={policy:set() for policy in POLICIES}
    published_domain_policies={}
    previous_rule_count=0
    baseline_conflict_holds=[]
    for policy in POLICIES:
        for line in previous_published[policy]:
            if line.startswith("DOMAIN,"):
                rule_sets[policy].add(("exact_candidate",line[7:].lower()))
            elif line.startswith("DOMAIN-SUFFIX,"):
                rule_sets[policy].add(("suffix_candidate",line[14:].lower()))
            else:
                raise ValueError("unsupported existing published rule: "+line)
            domain=line.split(",",1)[1].lower()
            if domain in published_domain_policies and published_domain_policies[domain]!=policy:
                raise ValueError("existing published domain appears under multiple policies: "+domain)
            published_domain_policies[domain]=policy
            previous_rule_count+=1
    if previous_rule_count>30000:
        raise ValueError("existing published rules exceed the 30,000 hard cap; refusing destructive truncation")
    seen=dict(published_domain_policies)
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
        engine=str(item.get("decision_engine",""))
        if engine not in {"deterministic-domain-audit/3.0","deterministic-domain-audit/4.0","deterministic-domain-audit/4.1"}:
            raise ValueError("approved record was not produced by a supported deterministic reviewer: "+domain)
        if domain in seen and seen[domain]!=policy:
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
        scope=str(item.get("source_entry_type","exact_candidate"))
        if scope not in {"exact_candidate","suffix_candidate"}:
            raise ValueError("unsupported approved domain scope: "+domain)
        archived_line=("DOMAIN-SUFFIX," if scope=="suffix_candidate" else "DOMAIN,")+domain
        if policy=="REJECT" and not reject_rule_authorized(archived_line,previously_published_reject,manual_reject_approvals):
            held+=1
            continue
        if (policy,archived_line) in config_conflict_archived:
            held+=1
            continue
        if (policy,archived_line) in archived_deleted:
            held+=1
            continue
        if domain in published_domain_policies:
            approved+=1
            continue
        if item.get("lifecycle_hold") and not lifecycle_active:
            held_line=("DOMAIN-SUFFIX," if scope=="suffix_candidate" else "DOMAIN,")+domain
            if held_line not in previous_published[policy]:
                raise ValueError("lifecycle-held rule is not present in the previous published artifact: "+domain)
            seen[domain]=policy
            rule_sets[policy].add((scope,domain))
            approved+=1
            continue
        if scope=="suffix_candidate":
            if engine not in {"deterministic-domain-audit/4.0","deterministic-domain-audit/4.1"}:
                raise ValueError("legacy exact-only review cannot publish suffix scope: "+domain)
            valid=[ev for ev in valid if ev.get("entry_type")=="suffix_candidate"]
        required=set(required_by_policy.get(policy,[]))
        confidence=float(item.get("confidence",0))
        _,source_ids,publishers,effective_groups,qualified=evidence_gate(
            valid,scoring.get("source_weights",{}),minimum,threshold,required,correlated_pairs
        )
        if not qualified or confidence<threshold:
            raise ValueError("approved record no longer meets current independent-evidence gate: "+domain)
        if int(item.get("source_count",0))<minimum:
            raise ValueError("approved record source count below minimum: "+domain)
        if any(item.get(key)!="PASS" for key in ("duplicate_check","conflict_check","risk_check")):
            raise ValueError("approved record failed a local safety gate: "+domain)
        # Apply the exact same config-scope gate to newly approved candidates
        # before they enter the queue or published output. This is broader than
        # policy-conflict detection: same-policy scope overlaps are also excluded.
        candidate_line=("DOMAIN-SUFFIX," if scope=="suffix_candidate" else "DOMAIN,")+domain
        scope_result=classify_rule(policy,candidate_line,config_rules,config_skip_proxy,prepared_config_rules)
        if scope_result["status"]!="NO_CONFLICT":
            held+=1
            baseline_conflict_holds.append({
                "domain":domain,"policy":policy,"scope":scope,
                "status":scope_result["status"],"reason":scope_result["reason"],
                "config_line":scope_result.get("config_line"),
                "config_rule":scope_result.get("config_rule"),
                "effective_config_policy":scope_result.get("effective_policy")
            })
            continue
        if scope=="suffix_candidate":
            local_status,reason=inspect_suffix_scope(
                domain,policy,index,conditional,protected,parse_skip_proxy(base)
            )
            if local_status:
                held+=1
                baseline_conflict_holds.append({"domain":domain,"policy":policy,"scope":scope,"status":local_status,"reason":reason})
                continue
        local_status,reason=inspect(domain,index,conditional,base,protected,policy,candidate_suffix=(scope=="suffix_candidate"))
        if local_status:
            held+=1
            baseline_conflict_holds.append({"domain":domain,"policy":policy,"scope":scope,"status":local_status,"reason":reason})
            continue
        seen[domain]=policy
        new_approved[policy].add((scope,domain))
        approved+=1

    OUT.mkdir(parents=True,exist_ok=True)
    queue_path=OUT/"pending_queue.json"
    prior_queue=json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.exists() else {"schema_version":1,"items":[]}
    queue_map={}
    for queued in prior_queue.get("items",[]):
        key=(str(queued.get("policy","")).upper(),str(queued.get("scope","exact_candidate")),str(queued.get("domain","")).lower())
        if key[0] in POLICIES and key[1] in {"exact_candidate","suffix_candidate"} and key[2]:
            queued_line=("DOMAIN-SUFFIX," if key[1]=="suffix_candidate" else "DOMAIN,")+key[2]
            if key[0]=="REJECT" and not reject_rule_authorized(queued_line,previously_published_reject,manual_reject_approvals):
                continue
            if (key[0],queued_line) not in archived_deleted:
                queue_map[key]=queued
    for policy in POLICIES:
        for scope,domain in sorted(new_approved[policy]):
            queue_map.setdefault((policy,scope,domain),{
                "policy":policy,"scope":scope,"domain":domain,
                "queued_at":datetime.now(timezone.utc).isoformat(),
                "reason":"Approved rule waiting for published capacity"
            })
    queued_domains={}
    for key in list(queue_map):
        policy,scope,domain=key
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("invalid domain in pending queue: "+domain)
        if domain in published_domain_policies:
            if published_domain_policies[domain]!=policy:
                raise ValueError("pending queue policy conflicts with a published rule: "+domain)
            queue_map.pop(key,None)
            continue
        prior_key=queued_domains.get(domain)
        if prior_key and prior_key!=(policy,scope):
            raise ValueError("pending queue contains cross-policy or cross-scope duplicate: "+domain)
        queued_domains[domain]=(policy,scope)
    for policy in POLICIES:
        for scope,domain in rule_sets[policy]:
            queue_map.pop((policy,scope,domain),None)
    promoted=promote_queue_to_capacity(rule_sets,queue_map,previous_rule_count,30000)
    for policy in POLICIES:
        for scope,domain in sorted(rule_sets[policy]):
            queue_map.pop((policy,scope,domain),None)
    queue_path.write_text(json.dumps({
        "schema_version":1,
        "max_published_rules":30000,
        "queued_count":len(queue_map),
        "items":[queue_map[key] for key in sorted(queue_map)]
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rule_lifecycle={}
    for policy in sorted(POLICIES):
        output_path=OUT/(policy.lower()+".list")
        existed=output_path.exists()
        previous_lines=set(output_path.read_text(encoding="utf-8").splitlines()) if existed else set()
        lines=[("DOMAIN-SUFFIX," if scope=="suffix_candidate" else "DOMAIN,")+domain for scope,domain in sorted(rule_sets[policy])]
        current_lines=set(lines)
        added=sorted(current_lines-previous_lines)
        removed=sorted(previous_lines-current_lines)
        previous_text="\n".join(sorted(previous_lines))+("\n" if previous_lines else "")
        current_text="\n".join(lines)+("\n" if lines else "")
        rule_lifecycle[policy]={
            "previous_count":len(previous_lines),
            "current_count":len(current_lines),
            "added_count":len(added),
            "removed_count":len(removed),
            "previous_sha256":hashlib.sha256(previous_text.encode("utf-8")).hexdigest(),
            "current_sha256":hashlib.sha256(current_text.encode("utf-8")).hexdigest(),
            "added_sample":added[:10],
            "removed_sample":removed[:10],
            "baseline_initialized":not existed
        }
        output_path.write_text(current_text,encoding="utf-8")
    expected_outputs={policy.lower()+".list" for policy in POLICIES}
    actual_outputs={item.name for item in OUT.glob("*.list")}
    if actual_outputs!=expected_outputs:
        raise ValueError("rule-set output directory contains unexpected or missing policy lists")
    candidate_matrix_path=ROOT/"sources/source_candidates.json"
    candidate_matrix=read_document(candidate_matrix_path,"candidates",{"candidates":[]})
    manifest={
        "schema_version":2,
        "source_ledger":"sources/domain_reviews.json",
        "current_source_snapshot":"data/candidates.json",
        "artifact_scope":"standalone_rulesets_only",
        "outputs":["direct.list","proxy.list","reject.list"],
        "review_engine":"deterministic-domain-audit/4.1",
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
        "published_rule_total":sum(len(rule_sets[policy]) for policy in POLICIES),
        "max_published_rules":30000,
        "queued_rule_total":len(queue_map),
        "baseline_conflict_hold_count":len(baseline_conflict_holds),
        "baseline_conflict_hold_sample":baseline_conflict_holds[:100],
        "pending_queue":"rulesets/pending_queue.json",
        "rule_lifecycle":rule_lifecycle,
        "reviewed_total":len(reviews),
        "approved_total":approved,
        "held_total":held,
        "reject_manual_approval_required":True,
        "reject_manual_approval_count":len(manual_reject_approvals),
        "reject_manual_hold_count":sum(1 for item in reviews if str(item.get("status",""))=="APPROVED" and str(item.get("policy","")).upper()=="REJECT" and (("DOMAIN-SUFFIX," if item.get("source_entry_type")=="suffix_candidate" else "DOMAIN,")+str(item.get("domain","")).lower().rstrip(".")) not in previously_published_reject and (("DOMAIN-SUFFIX," if item.get("source_entry_type")=="suffix_candidate" else "DOMAIN,")+str(item.get("domain","")).lower().rstrip(".")) not in manual_reject_approvals),
        "status_count":dict(sorted(status_counts.items())),
        "deterministic_review_progress":{
            "candidate_total":len(reviews),
            "approved_total":approved,
            "held_total":held,
            "status_count":dict(sorted(status_counts.items()))
        },
        "format":"Standalone Shadowrocket domain RULE-SET lists: DOMAIN,<domain> and DOMAIN-SUFFIX,<domain>; source scope is preserved and policy is assigned by the RULE-SET reference.",
        "import_instruction":"Optionally reference each published raw list URL in the user-managed Shadowrocket [Rule] section with RULE-SET,<raw URL>,<matching policy>. This automation does not edit the user config.",
        "limitations":[
            "All supported domain scopes are eligible: exact DOMAIN requires corroborated current domain evidence; DOMAIN-SUFFIX requires at least two independent current publishers explicitly listing the same suffix scope. Source scope is preserved.",
            "A domain is published only when at least two distinct configured publishers and source groups agree on its routing policy; a single-source candidate remains under review.",
            "Lineage status is retained as provenance metadata, not a blanket publication veto; source overlap is a correlation signal, not proof of identical domain ancestry.",
            "Single-label root suffixes are excluded during source parsing. Suffix publication is blocked when it intersects conflicting baseline rules, conditional rules, or protected hosts/suffixes.",
            "Static checks do not replace Shadowrocket device testing."
        ]
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
