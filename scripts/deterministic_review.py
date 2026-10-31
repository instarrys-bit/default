#!/usr/bin/env python3
from __future__ import annotations
import json,re,sys
from pathlib import Path
from datetime import datetime,timezone
from domain_rule_engine import RuleIndex,load_domain_rules
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"sources/baseline/ss.conf"
POLICY=ROOT/"sources/domain_sources.json"
PROTECTED=ROOT/"sources/protected_domains.json"
CANDIDATES=ROOT/"data/candidates.json"
OUTPUT=ROOT/"sources/domain_reviews.json"
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
COND_RE=re.compile(r"(DOMAIN-SUFFIX|DOMAIN),([A-Za-z0-9.-]+)",re.I)
def fail(msg): raise SystemExit("ERROR: "+msg)
def section(text,name,next_name):
    if text.count(name)!=1 or text.count(next_name)!=1: fail("cannot isolate "+name)
    return text.split(name,1)[1].split(next_name,1)[0]
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
def inspect(domain,rules,conditional,base,protected):
    hits=rules.matches_host(domain)
    if hits:
        winner=hits[0]
        return ("DUPLICATE" if winner.policy=="REJECT" else "CONFLICT",
                "Existing first-match "+winner.kind+" "+winner.domain+" => "+winner.policy+" (line "+str(winner.line)+")")
    for _,raw in conditional:
        for kind,match in COND_RE.findall(raw):
            match=match.lower().strip(".")
            applies=(domain==match or (kind.upper()=="DOMAIN-SUFFIX" and domain.endswith("."+match)))
            if applies: return "REVIEW","Candidate intersects an existing conditional AND/OR/NOT domain rule"
    for entry in protected.get("protected_exact",[]):
        if domain==entry.lower(): return "RISK_HOLD","Exact host is on the critical-function protection list"
    for suffix in protected.get("protected_suffixes",[]):
        if overlaps(domain,suffix): return "RISK_HOLD","Candidate intersects protected suffix "+suffix
    rule_block=section(base,"[Rule]","[Host]")
    for raw in rule_block.splitlines():
        line=raw.strip()
        if not line or line.startswith("#"): continue
        upper=line.upper()
        if upper.startswith("DOMAIN-KEYWORD,"):
            fields=line.split(",",2)
            if len(fields)==3 and fields[1].lower() in domain:
                pol=fields[2].strip().upper()
                return ("ALREADY_COVERED" if pol=="REJECT" else "CONFLICT"),"Matches existing DOMAIN-KEYWORD => "+pol
        if upper.startswith("URL-REGEX,"):
            fields=line.rsplit(",",1)
            if len(fields)!=2: return "REVIEW","Malformed URL-REGEX cannot be evaluated"
            try: pattern=re.compile(fields[0][len("URL-REGEX,"):])
            except re.error: return "REVIEW","Existing URL-REGEX cannot be compiled"
            probes=("http://"+domain+"/","https://"+domain+"/","http://"+domain+"/multifetch?dms=","http://"+domain+"/fetch?dm=","http://"+domain+"/d?dn=","http://"+domain+"/httpdns/")
            if any(pattern.search(x) for x in probes):
                pol=fields[1].strip().upper()
                return ("ALREADY_COVERED" if pol=="REJECT" else "CONFLICT"),"Matches existing URL-REGEX => "+pol
    for item in parse_skip_proxy(base):
        if "/" in item or ":" in item: continue
        if item.startswith("*."):
            root=item[2:]
            if domain==root or domain.endswith("."+root): return "CONFLICT","Matches skip-proxy direct-bypass entry "+item
        elif domain==item: return "CONFLICT","Matches skip-proxy direct-bypass entry "+item
    return None,None
def main():
    source_cfg=json.loads(POLICY.read_text(encoding="utf-8"))
    protected=json.loads(PROTECTED.read_text(encoding="utf-8"))
    collected=json.loads(CANDIDATES.read_text(encoding="utf-8"))
    config=CONFIG.read_text(encoding="utf-8")
    start="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"
    end="# END GPT-REVIEWED DOMAIN RULES (managed)"
    lines=config.splitlines(keepends=True)
    a=[i for i,x in enumerate(lines) if x.strip()==start]
    b=[i for i,x in enumerate(lines) if x.strip()==end]
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed rule block markers invalid")
    base="".join(lines[:a[0]]+lines[b[0]+1:])
    rules,conditional,ignored=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    score_cfg=source_cfg["scoring"]
    threshold=float(score_cfg["minimum_confidence"])
    source_weights=score_cfg["source_weights"]
    minimum=int(score_cfg["minimum_independent_sources"])
    now=datetime.now(timezone.utc).isoformat()
    if OUTPUT.exists():
        prior=json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        prior={"schema_version":1,"reviews":[]}
    review_map={x["domain"]:x for x in prior.get("reviews",[])}
    run_counts={}
    for item in collected.get("candidates",[]):
        domain=str(item.get("domain","")).lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain): fail("invalid candidate domain: "+domain)
        evidence=item.get("evidence",[])
        source_ids={x.get("source_id") for x in evidence if x.get("source_id") and x.get("currently_listed",True) is not False}
        confidence=round(min(1.0,sum(float(source_weights.get(source_id,0)) for source_id in source_ids)),2)
        status,reason=inspect(domain,index,conditional,base,protected)
        if status is None:
            if len(source_ids)<minimum or confidence<threshold:
                status="REVIEW"; reason="Independent-source corroboration below configured confidence threshold"
            else:
                status="APPROVED"; reason="Configured primary domain-only source meets the 0.26 threshold; optional independent corroboration is recorded when present"
        review_map[domain]={
            "domain":domain,"classification":"REJECT","policy":"REJECT","confidence":confidence,
            "status":status,"reason":reason,"evidence":evidence,"source_count":len(source_ids),
            "duplicate_check":"PASS" if status not in {"DUPLICATE","ALREADY_COVERED"} else status,
            "conflict_check":"PASS" if status not in {"CONFLICT","REVIEW"} else status,
            "risk_check":"VETO" if status=="RISK_HOLD" else "PASS",
            "decision_engine":"deterministic-domain-audit/1.1","reviewed_at":now,
            "config_baseline":"managed-block-excluded"
        }
        run_counts[status]=run_counts.get(status,0)+1
    reviews=sorted(review_map.values(),key=lambda x:x["domain"])
    total_counts={}
    for item in reviews: total_counts[item["status"]]=total_counts.get(item["status"],0)+1
    OUTPUT.write_text(json.dumps({
        "schema_version":1,"engine":"deterministic-domain-audit/1.1","updated_at":now,
        "source_snapshot":collected.get("sources",[]),"run_counts":run_counts,
        "counts":total_counts,"reviews":reviews
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Deterministic review complete: "+json.dumps(run_counts,ensure_ascii=False,sort_keys=True))
    print("Historical ledger entries: "+str(len(reviews))+"; candidates reviewed this run: "+str(len(collected.get("candidates",[])))+" (no 100-item cap).")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
