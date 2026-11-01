#!/usr/bin/env python3
"""Collect policy-labelled domain evidence from every enabled registered source."""
from __future__ import annotations
import hashlib,json,re,sys,time,urllib.error,urllib.request
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone
from source_registry import validate_registry

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/"sources/domain_sources.json"
BUFFER=ROOT/"data/domain_candidates.json"
SNAPSHOT_DIR=ROOT/"data/source_snapshots"
OUTPUT=ROOT/"data/candidates.json"
PENDING=ROOT/"data/source_pending.json"
LEGACY_SNAPSHOTS={
    "sr-adblock-domain-lite":ROOT/"data/primary_snapshot.txt",
    "hagezi-domains-pro":ROOT/"data/secondary_snapshot.txt",
}
MAX_BYTES=30_000_000
MAX_CHANGE_RATIO=0.10
MIN_CHANGE_ABSOLUTE=10
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def fetch(url):
    parsed=urlparse(url)
    if parsed.scheme!="https" or parsed.hostname!="raw.githubusercontent.com" or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError("source URL must be HTTPS raw.githubusercontent.com: "+url)
    req=urllib.request.Request(url,headers={"User-Agent":"Shadowrocket-Deterministic-Audit/1.3"})
    transient_http={408,425,429,500,502,503,504}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                final=urlparse(response.geturl())
                if response.status!=200 or final.scheme!="https" or final.hostname!="raw.githubusercontent.com":
                    raise ValueError("unexpected source response: "+response.geturl())
                data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:
                raise ValueError("source exceeds byte limit: "+url)
            return data
        except urllib.error.HTTPError as error:
            if error.code not in transient_http or attempt==2:
                raise
        except (urllib.error.URLError,TimeoutError) as error:
            if attempt==2:
                raise
        delay=2**(attempt+1)
        print(f"Transient source fetch failure; retry {attempt+2}/3 in {delay}s: {url}",file=sys.stderr)
        time.sleep(delay)
    raise RuntimeError("unreachable source fetch retry state")

def check_source_delta(previous,current,label,ratio=MAX_CHANGE_RATIO,minimum_absolute=MIN_CHANGE_ABSOLUTE):
    added=current-previous
    removed=previous-current
    changed=len(added)+len(removed)
    allowed=max(minimum_absolute,int(len(previous)*ratio))
    if previous and changed>allowed:
        raise ValueError(f"{label} source drift exceeds automatic safety limit: {len(added)} added + {len(removed)} removed = {changed}; limit {allowed}")
    return added,removed

def bootstrap_source_domains(source,source_id,bootstrapped_sources,domains,added):
    """Seed a primary source once even when a snapshot already exists from an earlier run."""
    if source.get("bootstrap_enqueue",False) and source.get("role")=="primary_candidate_source" and source_id not in bootstrapped_sources:
        bootstrapped_sources.add(source_id)
        return set(domains),True
    return set(added),False

def parse_domain_list(data,allow_leading_dot=False):
    result={}
    for number,raw in enumerate(data.decode("utf-8-sig").splitlines(),1):
        value=raw.strip()
        if not value or value.startswith(("#","!")):
            continue
        is_suffix=value.startswith(".")
        if is_suffix and not allow_leading_dot:
            raise ValueError(f"leading-dot suffix not permitted at line {number}")
        if is_suffix:
            value=value[1:]
        value=value.lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(value):
            if "." not in value:
                continue
            raise ValueError(f"unsupported/non-domain line {number}: {raw[:120]!r}")
        scope="suffix_candidate" if is_suffix else "exact_candidate"
        if value in result:
            if result[value]!=scope:
                raise ValueError(f"same domain appears with conflicting DOMAIN scope: {value}")
            continue
        result[value]=scope
    if not result:
        raise ValueError("domain-only source yielded no domains")
    return result

def parse_adblock(data):
    result={}
    rule=re.compile(r"^\|\|([a-z0-9.-]+)\^")
    for raw in data.decode("utf-8-sig").splitlines():
        value=raw.strip()
        if not value or value.startswith(("!","[","@@")):
            continue
        match=rule.match(value.lower())
        if not match:
            continue
        domain=match.group(1).rstrip(".")
        if DOMAIN_RE.fullmatch(domain):
            result[domain]="exact_candidate"
    if not result:
        raise ValueError("Adblock source yielded no domain rules")
    return result


def parse_shadowrocket_domain_rules(data,source):
    """Read only explicit DOMAIN / DOMAIN-SUFFIX rules; never coerce other rule types."""
    result={}
    expected=str(source.get("classification","")).upper()
    for number,raw in enumerate(data.decode("utf-8-sig").splitlines(),1):
        value=raw.split("#",1)[0].strip()
        if not value:
            continue
        fields=[x.strip() for x in value.split(",")]
        kind=fields[0].upper()
        if kind not in {"DOMAIN","DOMAIN-SUFFIX"}:
            continue
        if len(fields) not in (2,3):
            raise ValueError(f"malformed {kind} rule at line {number}")
        domain=fields[1].lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain):
            if kind=="DOMAIN-SUFFIX" and "." not in domain:
                continue
            raise ValueError(f"invalid domain in {kind} rule at line {number}: {fields[1]!r}")
        if len(fields)==3:
            action=fields[2].upper()
            if action not in {"DIRECT","PROXY","REJECT"}:
                raise ValueError(f"unsupported action in domain rule at line {number}: {fields[2]!r}")
            if action!=expected:
                raise ValueError(f"domain rule policy {action} conflicts with source classification {expected} at line {number}")
        scope="suffix_candidate" if kind=="DOMAIN-SUFFIX" else "exact_candidate"
        if domain in result:
            if result[domain]!=scope:
                raise ValueError(f"same domain appears with conflicting DOMAIN scope: {domain}")
            continue
        result[domain]=scope
    if not result:
        raise ValueError("Shadowrocket source yielded no exact DOMAIN / DOMAIN-SUFFIX rules")
    return result


def parse_quantumult_domain_rules(data,source):
    """Extract only host / host-suffix entries with an explicit supported action."""
    result={}
    expected=str(source.get("classification","")).upper()
    aliases={str(k).upper():str(v).upper() for k,v in source.get("policy_action_map",{}).items()}
    for number,raw in enumerate(data.decode("utf-8-sig").splitlines(),1):
        value=raw.split("#",1)[0].strip()
        if not value:
            continue
        fields=[x.strip() for x in value.split(",")]
        kind=fields[0].upper()
        if kind not in {"HOST","HOST-SUFFIX"}:
            continue
        if len(fields)<3:
            raise ValueError(f"malformed {kind} rule at line {number}")
        domain=fields[1].lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain):
            if kind=="HOST-SUFFIX" and "." not in domain:
                continue
            raise ValueError(f"invalid domain in {kind} rule at line {number}: {fields[1]!r}")
        raw_action=fields[2].upper()
        action=aliases.get(raw_action,raw_action)
        if action not in {"DIRECT","PROXY","REJECT"}:
            raise ValueError(f"unsupported action in {kind} rule at line {number}: {fields[2]!r}")
        if action!=expected:
            raise ValueError(f"domain rule policy {action} conflicts with source classification {expected} at line {number}")
        scope="suffix_candidate" if kind=="HOST-SUFFIX" else "exact_candidate"
        if domain in result:
            if result[domain]!=scope:
                raise ValueError(f"same domain appears with conflicting HOST scope: {domain}")
            continue
        result[domain]=scope
    if not result:
        raise ValueError("Quantumult X source yielded no exact HOST / HOST-SUFFIX rules")
    return result

def parse_source(data,source):
    fmt=source.get("format")
    if fmt=="domain-only":
        return parse_domain_list(data,allow_leading_dot=bool(source.get("allow_leading_dot",False)))
    if fmt=="adblock-domain-rules":
        return parse_adblock(data)
    if fmt=="shadowrocket-domain-rules":
        return parse_shadowrocket_domain_rules(data,source)
    if fmt=="quantumult-domain-rules":
        return parse_quantumult_domain_rules(data,source)
    raise ValueError("unsupported source format for "+str(source.get("id"))+": "+str(fmt))

def snapshot_path(source_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}",source_id):
        raise ValueError("unsafe source ID for snapshot filename: "+source_id)
    return SNAPSHOT_DIR/(source_id+".txt")

def read_snapshot(source_id):
    path=snapshot_path(source_id)
    if path.exists():
        return {x.strip().lower() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}
    legacy=LEGACY_SNAPSHOTS.get(source_id)
    if legacy and legacy.exists():
        return {x.strip().lower() for x in legacy.read_text(encoding="utf-8").splitlines() if x.strip()}
    return None

def main():
    cfg=json.loads(SOURCES.read_text(encoding="utf-8"))
    buf=json.loads(BUFFER.read_text(encoding="utf-8")) if BUFFER.exists() else {"candidates":[],"bootstrapped_sources":[]}
    pending_data=json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else {"schema_version":1,"sources":{}}
    pending_sources=dict(pending_data.get("sources",{}))
    bootstrapped_sources=set(buf.get("bootstrapped_sources",[]))
    by_id=validate_registry(cfg)
    enabled=[source for source in cfg["sources"] if source.get("enabled",True) is not False]
    if not enabled:
        raise ValueError("no enabled sources are configured")
    now=datetime.now(timezone.utc).isoformat()
    previous_output=json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"sources":[]}
    previous_hashes={str(x.get("id")):str(x.get("sha256")) for x in previous_output.get("sources",[]) if x.get("id") and x.get("sha256")}
    source_data={}
    deltas={}
    quarantined=[]
    # Isolate established sources with fetch, parse, or abnormal-delta failures.
    # A large update is accepted only after the exact same payload is observed twice.
    for source in enabled:
        sid=source["id"]
        previous=read_snapshot(sid)
        try:
            payload=fetch(source["url"])
            digest=hashlib.sha256(payload).hexdigest()
            domains=parse_source(payload,source)
            minimum=int(source.get("minimum_entries",1))
            if len(domains)<minimum:
                raise ValueError(f"{sid} unexpectedly small or truncated: {len(domains)} < {minimum}")
        except (OSError,urllib.error.URLError,TimeoutError,ValueError) as error:
            pending_sources.pop(sid,None)
            prior_digest=previous_hashes.get(sid)
            if previous is None or not prior_digest:
                raise ValueError(f"{sid} has no committed baseline; cannot safely isolate its first collection failure: {error}") from error
            source_data[sid]={"source":source,"sha256":prior_digest,"domains":{},"previous":previous,"stale":True,"error":str(error)[:500]}
            deltas[sid]={"added":set(),"removed":set(),"bootstrap":False,"bootstrap_enqueued":False}
            quarantined.append(sid)
            continue

        if previous is None:
            added=set()
            removed=set()
            bootstrap=True
            pending_sources.pop(sid,None)
        else:
            try:
                added,removed=check_source_delta(previous,set(domains),sid)
                pending_sources.pop(sid,None)
            except ValueError as error:
                pending=pending_sources.get(sid,{})
                confirmations=int(pending.get("confirmations",0))+1 if pending.get("sha256")==digest else 1
                if confirmations<2:
                    pending_sources[sid]={"sha256":digest,"confirmations":confirmations,"entries":len(domains),"first_seen":pending.get("first_seen",now),"last_seen":now}
                    prior_digest=previous_hashes.get(sid)
                    if not prior_digest:
                        raise ValueError(f"{sid} has an abnormal first delta but no committed hash baseline") from error
                    source_data[sid]={"source":source,"sha256":prior_digest,"domains":{},"previous":previous,"stale":True,"error":str(error)[:500],"pending_confirmations":confirmations}
                    deltas[sid]={"added":set(),"removed":set(),"bootstrap":False,"bootstrap_enqueued":False}
                    quarantined.append(sid)
                    continue
                # Stable, repeated content is allowed through the normal policy/evidence gates.
                added=set(domains)-previous
                removed=previous-set(domains)
                pending_sources.pop(sid,None)
            bootstrap=False
        added,bootstrap_enqueued=bootstrap_source_domains(source,sid,bootstrapped_sources,set(domains),added)
        source_data[sid]={"source":source,"sha256":digest,"domains":domains,"previous":previous,"stale":False}
        deltas[sid]={"added":added,"removed":removed,"bootstrap":bootstrap,"bootstrap_enqueued":bootstrap_enqueued}

    queue={x["domain"]:x for x in buf.get("candidates",[])}
    # Only explicitly designated candidate sources enqueue new entries.
    for sid,info in source_data.items():
        if info["stale"] or info["source"].get("role")!="primary_candidate_source":
            continue
        for domain in sorted(deltas[sid]["added"]):
            if domain not in queue:
                queue[domain]={"domain":domain,"source_id":sid,"first_seen":now}
    rows=[]
    for domain,item in sorted(queue.items()):
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("invalid domain in candidate buffer: "+domain)
        evidence=[]
        scopes=[]
        policies=set()
        for sid,info in source_data.items():
            entry_type=info["domains"].get(domain)
            if entry_type is None:
                continue
            source=info["source"]
            policy=str(source["classification"]).upper()
            policies.add(policy)
            scopes.append(entry_type)
            evidence.append({
                "source_id":sid,
                "entry_type":entry_type,
                "publisher":source["publisher"],
                "independence_group":source["independence_group"],
                "lineage_status":source["lineage_status"],
                "policy_evidence":source.get("policy_evidence","documented_policy"),
                "upstream_repositories":source.get("upstream_repositories",[]),
                "classification":policy,
                "url":source["url"],
                "sha256":info["sha256"],
                "currently_listed":True
            })
        classification=next(iter(policies)) if len(policies)==1 else ("CONFLICT" if policies else str(item.get("classification","REVIEW")).upper())
        source_entry_type="suffix_candidate" if "suffix_candidate" in scopes else "exact_candidate"
        rows.append({
            "domain":domain,
            "source_entry_type":source_entry_type,
            "classification":classification,
            "candidate_policies":sorted(policies),
            "evidence":evidence,
            "first_seen":item.get("first_seen")
        })
    SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True)
    for sid,info in source_data.items():
        if info["stale"]:
            continue
        path=snapshot_path(sid)
        path.write_text("\n".join(sorted(info["domains"]))+"\n",encoding="utf-8")
    BUFFER.write_text(json.dumps({"schema_version":2,"updated_at":now,"bootstrapped_sources":sorted(bootstrapped_sources),"candidates":list(queue.values())},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PENDING.parent.mkdir(parents=True,exist_ok=True)
    PENDING.write_text(json.dumps({"schema_version":1,"updated_at":now,"sources":pending_sources},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "schema_version":3,
        "collected_at":now,
        "source_count":len(source_data),
        "quarantined_source_count":len(quarantined),
        "quarantined_sources":sorted(quarantined),
        "sources":[{"id":sid,"sha256":info["sha256"],"entries":len(info["previous"]) if info["stale"] and info["previous"] is not None else len(info["domains"]),"classification":info["source"]["classification"],"role":info["source"].get("role"),"lineage_status":info["source"]["lineage_status"],"upstream_repositories":info["source"].get("upstream_repositories",[]),"status":"STALE_QUARANTINED" if info["stale"] else "CURRENT","error":info.get("error"),"pending_confirmations":info.get("pending_confirmations",0),"new_entries":len(deltas[sid]["added"]),"removed_entries":len(deltas[sid]["removed"]),"baseline_initialized":deltas[sid]["bootstrap"],"bootstrap_enqueued":deltas[sid]["bootstrap_enqueued"]} for sid,info in sorted(source_data.items())],
        "candidate_count":len(rows),
        "policy_conflict_count":sum(1 for row in rows if row["classification"]=="CONFLICT"),
        "candidates":rows
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Multi-source collection complete: "+json.dumps({
        sid:{"entries":len(info["previous"]) if info["stale"] and info["previous"] is not None else len(info["domains"]),"added":len(deltas[sid]["added"]),"removed":len(deltas[sid]["removed"]),"status":"STALE_QUARANTINED" if info["stale"] else "CURRENT","baseline_initialized":deltas[sid]["bootstrap"]}
        for sid,info in sorted(source_data.items())
    },ensure_ascii=False,sort_keys=True))
    print(f"Queued candidates: {len(rows)}; cross-policy conflicts: {sum(1 for row in rows if row['classification']=='CONFLICT')}; quarantined sources: {len(quarantined)}; no candidate cap.")
if __name__=="__main__":
    try:
        main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as error:
        print("ERROR: "+str(error),file=sys.stderr)
        raise SystemExit(1)
