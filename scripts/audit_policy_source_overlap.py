#!/usr/bin/env python3
"""Measure domain-level overlap and policy contradictions across discovered candidate feeds.

This is an audit-only stage. It never registers sources, changes policy, or publishes rules.
"""
from __future__ import annotations
import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "sources/source_assessments.json"
OUTPUT = ROOT / "sources/policy_source_overlap.json"
REPORT = ROOT / "reports/policy-source-overlap.md"
MAX_BYTES = 2_000_000
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
RULE_RE = re.compile(r"^(?:DOMAIN|DOMAIN-SUFFIX),([^,\s]+)(?:,(?:DIRECT|PROXY|REJECT))?$", re.I)
QX_RE = re.compile(r"^(?:HOST|HOST-SUFFIX),([^,\s]+),(?:DIRECT|PROXY|REJECT|OUTSIDE)$", re.I)

def fetch(url: str, repository: str) -> bytes:
    p=urllib.parse.urlparse(url)
    parts=[x for x in p.path.split("/") if x]
    if p.scheme!="https" or p.hostname!="raw.githubusercontent.com" or len(parts)<4 or "/".join(parts[:2]).lower()!=repository.lower():
        raise ValueError("URL is not a repository-owned HTTPS raw GitHub file")
    req=urllib.request.Request(url,headers={"User-Agent":"Shadowrocket-Policy-Overlap-Audit/1.0"})
    with urllib.request.urlopen(req,timeout=15) as r:
        final=urllib.parse.urlparse(r.geturl())
        if r.status!=200 or final.scheme!="https" or final.hostname!="raw.githubusercontent.com":
            raise ValueError("unexpected response URL/status")
        data=r.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES: raise ValueError("source exceeds size limit")
    return data

def extract_domains(payload: bytes) -> set[str]:
    found=set()
    for raw in payload.decode("utf-8-sig",errors="replace").splitlines():
        line=raw.split("#",1)[0].strip()
        if not line or line.startswith(("!","#","[")): continue
        m=RULE_RE.fullmatch(line) or QX_RE.fullmatch(line)
        if m:
            d=m.group(1).lower().rstrip(".")
            if DOMAIN_RE.fullmatch(d): found.add(d)
            continue
        if line.startswith("."): line=line[1:]
        d=line.lower().rstrip(".")
        if DOMAIN_RE.fullmatch(d): found.add(d)
    return found

def build_report(assessments: dict, fetcher=fetch) -> dict:
    feeds=[]
    for item in assessments.get("assessments",[]):
        policy=item.get("policy_candidate")
        parser=item.get("parser_candidate")
        repo=item.get("repository","")
        if policy not in {"DIRECT","PROXY","REJECT"} or parser not in {"domain-only","adblock-domain-rules","shadowrocket-domain-rules","quantumult-domain-rules"} or not repo:
            continue
        payload=fetcher(item["url"],repo)
        domains=extract_domains(payload)
        feeds.append({"repository":repo,"policy":policy,"url":item["url"],"sha256":hashlib.sha256(payload).hexdigest(),"domains":domains})
    # A repository is one publisher: union its feeds before comparing publishers.
    grouped=defaultdict(set)
    urls=defaultdict(list)
    for f in feeds:
        grouped[(f["policy"],f["repository"])].update(f["domains"])
        urls[(f["policy"],f["repository"])].append(f["url"])
    overlaps=[]
    for policy in ("DIRECT","PROXY","REJECT"):
        pubs=sorted(r for p,r in grouped if p==policy)
        for i,left in enumerate(pubs):
            for right in pubs[i+1:]:
                a,b=grouped[(policy,left)],grouped[(policy,right)]
                shared=a&b
                overlaps.append({"policy":policy,"publishers":[left,right],"left_count":len(a),"right_count":len(b),"overlap_count":len(shared),"jaccard":round(len(shared)/len(a|b),6) if a|b else 0.0,"smaller_set_overlap":round(len(shared)/min(len(a),len(b)),6) if min(len(a),len(b)) else 0.0,"shared_domain_sample":sorted(shared)[:50]})
    by_domain=defaultdict(set)
    for (policy,repo),domains in grouped.items():
        for domain in domains: by_domain[domain].add(policy)
    contradictions=[{"domain":d,"policies":sorted(p)} for d,p in sorted(by_domain.items()) if len(p)>1]
    return {"schema_version":1,"feed_count":len(feeds),"publisher_counts":{p:len({r for q,r in grouped if q==p}) for p in ("DIRECT","PROXY","REJECT")},"overlaps":overlaps,"cross_policy_conflict_domain_count":len(contradictions),"cross_policy_conflict_sample":contradictions[:200],"activation_count":0,"activation_policy":"Audit-only. Overlap is not proof of common ancestry or independent provenance; no source is activated."}

def main():
    data=json.loads(INPUT.read_text(encoding="utf-8"))
    result=build_report(data)
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rows=["# Policy source overlap audit","","This report compares normalized domain sets across discovered publisher feeds. It is informational only: overlap does not prove common ancestry, and low overlap does not prove independence.","",f"- Feeds fetched: **{result['feed_count']}**",f"- Cross-policy conflict domains: **{result['cross_policy_conflict_domain_count']}**","", "| Policy | Publisher A | Publisher B | A domains | B domains | Shared | Smaller-set overlap | Jaccard |","|---|---|---|---:|---:|---:|---:|---:|"]
    for x in result["overlaps"]:
        rows.append(f"| {x['policy']} | {x['publishers'][0]} | {x['publishers'][1]} | {x['left_count']} | {x['right_count']} | {x['overlap_count']} | {x['smaller_set_overlap']:.1%} | {x['jaccard']:.1%} |")
    rows += ["","## Cross-policy contradictions","",f"Detected domains appearing under more than one policy: **{result['cross_policy_conflict_domain_count']}**",""]
    for x in result["cross_policy_conflict_sample"]: rows.append(f"- `{x['domain']}`: {', '.join(x['policies'])}")
    rows += ["","## Publication boundary","","This stage does not add sources to the active registry, does not approve domains, and does not alter the three rule sets. Two genuinely independent, verified publishers and all existing deterministic gates remain required.",""]
    REPORT.write_text("\n".join(rows),encoding="utf-8")
    print(json.dumps({"feeds":result["feed_count"],"publisher_counts":result["publisher_counts"],"overlap_pairs":len(result["overlaps"]),"cross_policy_conflicts":result["cross_policy_conflict_domain_count"],"activation_count":0},sort_keys=True))

if __name__=="__main__": main()
