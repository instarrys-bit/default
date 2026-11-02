#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,sys
from functools import lru_cache
from pathlib import Path
from datetime import datetime,timezone
from domain_rule_engine import RuleIndex,load_domain_rules,inspect_suffix_scope
from source_registry import validate_registry
from review_cursor import snapshot_digest,resume_index,checkpoint
from json_document_store import read_document,write_document
from audit_ruleset_config_overlap import scope_covers_candidate
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"
POLICY=ROOT/"sources/domain_sources.json"
PROTECTED=ROOT/"sources/protected_domains.json"
CANDIDATES=ROOT/"data/candidates.json"
OUTPUT=ROOT/"sources/domain_reviews.json"
CURSOR=ROOT/"sources/review_cursor.json"
SOURCE_MATRIX=ROOT/"sources/source_candidates.json"
LINEAGE_REPORT=ROOT/"reports/source-lineage-audit.json"
LIFECYCLE_STATE=ROOT/"rulesets/lifecycle_state.json"
RULESET_DIR=ROOT/"rulesets"
MAX_REVIEW_RECORDS=30_000_000
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
COND_RE=re.compile(r"(DOMAIN-SUFFIX|DOMAIN),([A-Za-z0-9.-]+)",re.I)
def fail(msg): raise SystemExit("ERROR: "+msg)

def validate_evidence(evidence, source_map, current_hashes, policy):
    """Keep only current evidence whose identity and policy match the trusted source registry."""
    valid=[]
    for item in evidence:
        source_id=str(item.get("source_id",""))
        source=source_map.get(source_id)
        if not source or source.get("enabled",True) is False:
            continue
        if item.get("currently_listed") is not True:
            continue
        if not current_hashes.get(source_id) or item.get("sha256")!=current_hashes[source_id]:
            continue
        if str(source.get("classification","")).upper()!=policy:
            continue
        if str(item.get("classification","")).upper()!=policy:
            continue
        if item.get("publisher")!=source.get("publisher"):
            continue
        if item.get("independence_group")!=source.get("independence_group",source.get("publisher")):
            continue
        if item.get("url")!=source.get("url"):
            continue
        if item.get("lineage_status")!=source.get("lineage_status"):
            continue
        if source.get("policy_evidence") is not None and item.get("policy_evidence")!=source.get("policy_evidence"):
            continue
        if item.get("upstream_repositories")!=source.get("upstream_repositories",[]):
            continue
        valid.append(item)
    return valid

def evidence_gate(evidence, source_weights, minimum, threshold, required_sources=(), correlated_pairs=()):
    """Count highly correlated publishers as one evidence group; unknown lineage is not a veto."""
    current=[item for item in evidence if item.get("source_id") and item.get("currently_listed") is True and item.get("lineage_status") in {"verified","partial","unverified"}]
    source_ids={str(item.get("source_id")) for item in current}
    publishers={str(item.get("publisher")) for item in current if item.get("publisher")}
    adjacency={publisher:set() for publisher in publishers}
    publisher_groups={}
    for item in current:
        publisher=str(item.get("publisher",""))
        group=str(item.get("independence_group",""))
        if publisher and group:
            if group in publisher_groups:
                other=publisher_groups[group]
                adjacency[publisher].add(other)
                adjacency[other].add(publisher)
            else:
                publisher_groups[group]=publisher
    for left,right in correlated_pairs:
        if left in adjacency and right in adjacency:
            adjacency[left].add(right)
            adjacency[right].add(left)
    groups=set()
    unseen=set(publishers)
    while unseen:
        first=unseen.pop()
        component={first}
        pending=[first]
        while pending:
            current_publisher=pending.pop()
            for neighbor in adjacency[current_publisher] & unseen:
                unseen.remove(neighbor)
                component.add(neighbor)
                pending.append(neighbor)
        groups.add(tuple(sorted(component)))
    confidence=round(min(1.0,sum(float(source_weights.get(source_id,0)) for source_id in source_ids)),2)
    required=set(required_sources)
    qualified=(len(source_ids)>=minimum and len(publishers)>=minimum and len(groups)>=minimum and required.issubset(source_ids) and confidence>=threshold)
    return confidence,source_ids,publishers,groups,qualified

def load_correlated_publishers():
    """Read same-policy high/near-duplicate relationships from the source candidate matrix."""
    matrix=json.loads(SOURCE_MATRIX.read_text(encoding="utf-8")) if SOURCE_MATRIX.exists() else {}
    pairs=set()
    for item in matrix.get("same_policy_domain_overlap",[]):
        if item.get("relation") not in {"high_overlap","near_duplicate"}: continue
        repos=item.get("repositories",[])
        if len(repos)==2 and repos[0]!=repos[1]: pairs.add(tuple(sorted((str(repos[0]),str(repos[1])))))
    # Shared upstream references are correlation warnings, not proof of common data ancestry.
    if LINEAGE_REPORT.exists() and POLICY.exists():
        lineage=json.loads(LINEAGE_REPORT.read_text(encoding="utf-8"))
        registry=json.loads(POLICY.read_text(encoding="utf-8"))
        publisher_by_id={str(item.get("id")):str(item.get("publisher")) for item in registry.get("sources",[])}
        for item in lineage.get("shared_upstream_pairs",[]):
            source_ids=item.get("sources",[])
            if len(source_ids)!=2: continue
            left=publisher_by_id.get(str(source_ids[0]))
            right=publisher_by_id.get(str(source_ids[1]))
            if left and right and left!=right: pairs.add(tuple(sorted((left,right))))
    return pairs

def atomic_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(path)
@lru_cache(maxsize=8)
def section(text,name,next_name):
    if text.count(name)!=1 or text.count(next_name)!=1: fail("cannot isolate "+name)
    return text.split(name,1)[1].split(next_name,1)[0]
@lru_cache(maxsize=8)
def parse_skip_proxy(text):
    if text.count("[General]")!=1 or text.count("[Rule]")!=1: fail("cannot isolate [General] section")
    block=text.split("[General]",1)[1].split("[Rule]",1)[0]
    for raw in block.splitlines():
        if raw.strip().lower().startswith("skip-proxy"):
            return [x.strip().lower() for x in raw.split("=",1)[1].split(",") if x.strip()]
    return []
def overlaps(domain, rule_domain):
    rule_domain=rule_domain.lower().strip(".")
    return domain==rule_domain or domain.endswith("."+rule_domain)

@lru_cache(maxsize=8)
def special_rule_lines(text):
    rule_block = section(text, "[Rule]", "[Host]")
    return tuple(
        line.strip() for line in rule_block.splitlines()
        if line.strip() and line.strip().upper().startswith(("DOMAIN-KEYWORD,", "URL-REGEX,"))
    )
def inspect(domain,rules,conditional,base,protected,candidate_policy=None,candidate_suffix=False):
    domain = domain.lower().rstrip(".")
    candidate_policy = str(candidate_policy or "").upper()
    candidate_scope = "suffix_candidate" if candidate_suffix else "exact_candidate"

    # Compare complete scopes only. No first-match winner or rule ordering is used.
    covering = [
        rule for rule in rules.rules
        if rule.policy != "REJECT" and scope_covers_candidate(candidate_scope, domain, rule.kind, rule.domain)
    ]
    if covering:
        policies = {rule.policy for rule in covering}
        evidence = "; ".join(
            rule.kind + " " + rule.domain + " => " + rule.policy
            for rule in covering
        )
        if len(policies) > 1:
            return "REVIEW", "Multiple explicit config scopes fully cover the candidate with different policies; no winner is selected: " + evidence
        covered_policy = next(iter(policies))
        status = "ALREADY_COVERED" if candidate_policy == covered_policy else "CONFLICT"
        return status, "Explicit config scope fully covers candidate (" + evidence + "); rule order is not evaluated"

    for _,raw in conditional:
        if raw.rsplit(",", 1)[-1].strip().upper() == "REJECT":
            continue
        for kind,match in COND_RE.findall(raw):
            match=match.lower().strip(".")
            if candidate_suffix:
                applies = (
                    match == domain or match.endswith("." + domain)
                    if kind.upper() == "DOMAIN"
                    else match == domain or match.endswith("." + domain) or domain.endswith("." + match)
                )
            else:
                applies = domain == match or (kind.upper() == "DOMAIN-SUFFIX" and domain.endswith("." + match))
            if applies:
                return "REVIEW","Candidate scope intersects an existing conditional AND/OR/NOT domain rule"

    for entry in protected.get("protected_exact",[]):
        host = entry.lower().strip(".")
        if host == domain or (candidate_suffix and host.endswith("." + domain)):
            return "RISK_HOLD","Candidate scope intersects the critical-function protection list at " + host
    for suffix in protected.get("protected_suffixes",[]):
        suffix = suffix.lower().strip(".")
        intersects = (
            domain == suffix or domain.endswith("." + suffix)
            or (candidate_suffix and suffix.endswith("." + domain))
        )
        if intersects:
            return "RISK_HOLD","Candidate intersects protected suffix " + suffix

    for line in special_rule_lines(base):
        upper=line.upper()
        if upper.startswith("DOMAIN-KEYWORD,"):
            fields=line.split(",",2)
            if len(fields)==3 and fields[2].strip().upper() != "REJECT" and fields[1].lower() in domain:
                if candidate_suffix:
                    return "REVIEW","Suffix candidate may intersect existing DOMAIN-KEYWORD rule"
                pol=fields[2].strip().upper()
                result="ALREADY_COVERED" if candidate_policy==pol else "CONFLICT"
                return result,"Matches existing DOMAIN-KEYWORD => "+pol
        if upper.startswith("URL-REGEX,"):
            fields=line.rsplit(",",1)
            if len(fields)!=2:
                return "REVIEW","Malformed URL-REGEX cannot be evaluated"
            pattern_text=fields[0][len("URL-REGEX,"):]
            try:
                re.compile(pattern_text)
            except re.error:
                return "REVIEW","Existing URL-REGEX cannot be compiled"
            slash=chr(92)+"/"
            if "[^"+slash+"]+" in pattern_text:
                continue
            prefixes=("^http:"+slash+slash,"^https?:"+slash+slash)
            prefix=next((item for item in prefixes if pattern_text.startswith(item)),None)
            if not prefix:
                continue
            host_pattern=pattern_text[len(prefix):].split(slash,1)[0]
            host_literal=host_pattern.replace(chr(92)+".",".")
            if host_literal.count(".")<2:
                continue
            try:
                host_regex=re.compile(r"^(?:"+host_pattern+r")$")
            except re.error:
                return "REVIEW","Existing URL-REGEX host pattern cannot be compiled"
            if fields[1].strip().upper() == "REJECT":
                continue
            if host_regex.fullmatch(domain):
                if candidate_suffix:
                    return "REVIEW","Suffix candidate may intersect host-specific URL-REGEX"
                pol=fields[1].strip().upper()
                result="ALREADY_COVERED" if candidate_policy==pol else "CONFLICT"
                return result,"Matches host-specific URL-REGEX => "+pol

    for item in parse_skip_proxy(base):
        if "/" in item or ":" in item:
            continue
        if item.startswith("*."):
            root=item[2:].strip(".")
            applies = domain == root or domain.endswith("." + root)
        else:
            applies = not candidate_suffix and domain == item
        if applies:
            result="ALREADY_COVERED" if candidate_policy=="DIRECT" else "CONFLICT"
            return result,"Matches fully covering skip-proxy direct-bypass entry "+item
    return None,None

def main():
    source_cfg=json.loads(POLICY.read_text(encoding="utf-8"))
    protected=json.loads(PROTECTED.read_text(encoding="utf-8"))
    collected=json.loads(CANDIDATES.read_text(encoding="utf-8"))
    config=CONFIG.read_text(encoding="utf-8")
    base=config
    rules,conditional,ignored=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    source_map=validate_registry(source_cfg)
    current_hashes={}
    for item in collected.get("sources",[]):
        source_id=str(item.get("id",""))
        digest=str(item.get("sha256",""))
        if not source_id or source_id in current_hashes or not re.fullmatch(r"[0-9a-f]{64}",digest):
            fail("source snapshot contains missing/duplicate ID or invalid SHA-256")
        current_hashes[source_id]=digest
    enabled_source_ids={sid for sid,source in source_map.items() if source.get("enabled",True) is not False}
    if set(current_hashes)!=enabled_source_ids:
        fail("source snapshot does not exactly match enabled source registry entries")
    score_cfg=source_cfg["scoring"]
    threshold=float(score_cfg["minimum_confidence"])
    source_weights=score_cfg["source_weights"]
    minimum=int(score_cfg["minimum_independent_sources"])
    now=datetime.now(timezone.utc).isoformat()
    correlated_pairs=load_correlated_publishers()
    if OUTPUT.exists():
        prior=read_document(OUTPUT,"reviews",{"schema_version":1,"reviews":[]})
    else:
        prior={"schema_version":1,"reviews":[]}
    review_map={x["domain"]:x for x in prior.get("reviews",[])}
    if len(review_map)>MAX_REVIEW_RECORDS:
        fail(f"historical review ledger exceeds hard limit: {len(review_map):,} > {MAX_REVIEW_RECORDS:,}")
    lifecycle_state=json.loads(LIFECYCLE_STATE.read_text(encoding="utf-8")) if LIFECYCLE_STATE.exists() else {}
    lifecycle_active=bool(lifecycle_state.get("active"))
    published_identities=set()
    for policy_name in ("direct","proxy","reject"):
        list_path=RULESET_DIR/(policy_name+".list")
        if not list_path.exists():
            continue
        for raw in list_path.read_text(encoding="utf-8").splitlines():
            line=raw.strip()
            if line.startswith("DOMAIN,"):
                published_identities.add((policy_name.upper(),line[7:],"exact_candidate"))
            elif line.startswith("DOMAIN-SUFFIX,"):
                published_identities.add((policy_name.upper(),line[14:],"suffix_candidate"))
    run_counts={}
    candidates=collected.get("candidates",[])
    if len(candidates)>MAX_REVIEW_RECORDS:
        fail(f"candidate review input exceeds hard limit: {len(candidates):,} > {MAX_REVIEW_RECORDS:,}")
    snapshot_sha256=snapshot_digest(collected.get("sources",[]),candidates)
    cursor_state=json.loads(CURSOR.read_text(encoding="utf-8")) if CURSOR.exists() else {}
    start_index=resume_index(cursor_state,snapshot_sha256,len(candidates))
    batch_size=5000
    for candidate_index,item in enumerate(candidates[start_index:],start=start_index):
        domain=str(item.get("domain","")).lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain): fail("invalid candidate domain: "+domain)
        policy=str(item.get("classification","")).upper()
        raw_evidence=item.get("evidence",[])
        candidate_policies={str(x).upper() for x in item.get("candidate_policies",[])}
        source_entry_type="exact_candidate"
        if policy=="CONFLICT" or len(candidate_policies)>1:
            evidence=[]
            for evidence_policy in ("DIRECT","PROXY","REJECT"):
                evidence.extend(validate_evidence(raw_evidence,source_map,current_hashes,evidence_policy))
            unique={(x.get("source_id"),x.get("sha256")):x for x in evidence}
            evidence=list(unique.values())
            confidence,source_ids,publishers,groups,_=evidence_gate(evidence,source_weights,minimum,threshold,(),correlated_pairs)
            status="POLICY_CONFLICT"
            reason="The same domain is listed by sources assigning different routing policies: "+", ".join(sorted(candidate_policies))
            policy="CONFLICT"
        elif policy not in {"DIRECT","PROXY","REJECT"}:
            evidence=[]
            confidence,source_ids,publishers,groups,_=evidence_gate([],source_weights,minimum,threshold,(),correlated_pairs)
            status="REVIEW"
            reason="No currently enabled source provides a supported policy classification"
        else:
            evidence=validate_evidence(raw_evidence,source_map,current_hashes,policy)
            required_sources=set(score_cfg.get("required_sources_by_policy",{}).get(policy,[]))
            suffix_evidence=[x for x in evidence if x.get("entry_type")=="suffix_candidate"]
            suffix_confidence,suffix_source_ids,suffix_publishers,suffix_groups,suffix_qualified=evidence_gate(
                suffix_evidence,source_weights,minimum,threshold,required_sources,correlated_pairs
            )
            if suffix_qualified:
                source_entry_type="suffix_candidate"
                evidence=suffix_evidence
                confidence,source_ids,publishers,groups,qualified=(
                    suffix_confidence,suffix_source_ids,suffix_publishers,suffix_groups,suffix_qualified
                )
            else:
                source_entry_type="exact_candidate"
                confidence,source_ids,publishers,groups,qualified=evidence_gate(evidence,source_weights,minimum,threshold,required_sources,correlated_pairs)
            scope_status,scope_reason=(None,None)
            if source_entry_type=="suffix_candidate":
                scope_status,scope_reason=inspect_suffix_scope(
                    domain,policy,index,conditional,protected,parse_skip_proxy(base)
                )
            if scope_status:
                status,reason=scope_status,scope_reason
            else:
                status,reason=inspect(domain,index,conditional,base,protected,policy,candidate_suffix=(source_entry_type=="suffix_candidate"))
            if status is None:
                if not qualified:
                    status="REVIEW"; reason="Current source identity, publisher, policy, independence, scope or confidence evidence is below configured threshold"
                else:
                    status="APPROVED"; reason="Policy and domain scope evidence agree across distinct configured publishers; lineage is recorded separately and is not a blanket veto; all local gates passed"
        new_record={
            "domain":domain,"source_entry_type":source_entry_type,"candidate_policies":sorted(candidate_policies),"classification":policy,"policy":policy,"confidence":confidence,
            "status":status,"reason":reason,"evidence":evidence,"source_count":len(source_ids),"publisher_count":len(publishers),"independence_group_count":len(groups),
            "rejected_evidence_count":len(raw_evidence)-len(evidence),
            "duplicate_check":"PASS" if status not in {"DUPLICATE","ALREADY_COVERED"} else status,
            "conflict_check":"PASS" if status not in {"CONFLICT","POLICY_CONFLICT","REVIEW"} else status,
            "risk_check":"VETO" if status=="RISK_HOLD" else "PASS",
            "decision_engine":"deterministic-domain-audit/4.1","reviewed_at":now,
            "config_authority":"shadowrocket/ss.conf"
        }
        previous_record=review_map.get(domain)
        previous_policy=str(previous_record.get("policy","")).upper() if previous_record else ""
        previous_scope=str(previous_record.get("source_entry_type","exact_candidate")) if previous_record else "exact_candidate"
        was_published=(previous_policy,domain,previous_scope) in published_identities
        if (not lifecycle_active and status=="REVIEW" and previous_record
            and previous_record.get("status")=="APPROVED" and was_published):
            new_record=dict(previous_record)
            new_record["lifecycle_hold"]={
                "status":"HELD_UNTIL_LIFECYCLE_ACTIVATION",
                "reason":"Temporary evidence insufficiency does not remove an already-published rule before the 5,000-rule lifecycle gate activates.",
                "checked_at":now
            }
        if domain not in review_map and len(review_map)>=MAX_REVIEW_RECORDS:
            fail(f"historical review ledger would exceed hard limit: {MAX_REVIEW_RECORDS:,}")
        review_map[domain]=new_record
        run_counts[status]=run_counts.get(status,0)+1
        if (candidate_index+1)%batch_size==0 or candidate_index+1==len(candidates):
            partial_reviews=sorted(review_map.values(),key=lambda x:x["domain"])
            partial_counts={}
            for record in partial_reviews: partial_counts[record["status"]]=partial_counts.get(record["status"],0)+1
            write_document(OUTPUT,{"schema_version":3,"engine":"deterministic-domain-audit/4.1","updated_at":now,"source_snapshot":collected.get("sources",[]),"run_counts":run_counts,"counts":partial_counts,"reviews":partial_reviews},"reviews")
            atomic_json(CURSOR,{**checkpoint(snapshot_sha256,len(candidates),candidate_index+1,batch_size),"updated_at":now,"last_checkpoint_domain":domain})
    reviews=sorted(review_map.values(),key=lambda x:x["domain"])
    total_counts={}
    for item in reviews: total_counts[item["status"]]=total_counts.get(item["status"],0)+1
    write_document(OUTPUT,{
        "schema_version":3,"engine":"deterministic-domain-audit/4.1","updated_at":now,
        "source_snapshot":collected.get("sources",[]),"run_counts":run_counts,
        "counts":total_counts,"reviews":reviews
    },"reviews")
    atomic_json(CURSOR,{**checkpoint(snapshot_sha256,len(candidates),len(candidates),batch_size,"complete"),"updated_at":now,"last_checkpoint_domain":candidates[-1].get("domain") if candidates else None})
    print("Deterministic review complete: "+json.dumps(run_counts,ensure_ascii=False,sort_keys=True))
    print("Review cursor: "+json.dumps({"status":"complete","candidate_count":len(candidates),"snapshot_sha256":snapshot_sha256,"correlated_publisher_pairs":len(correlated_pairs)},sort_keys=True))
    print("Historical ledger entries: "+str(len(reviews))+"; candidates reviewed this run: "+str(len(collected.get("candidates",[])))+" (hard ceiling: 30,000,000).")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
