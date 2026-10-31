#!/usr/bin/env python3
"""Filter newly captured domain candidates before they enter GPT review."""
from __future__ import annotations
import json,re
from pathlib import Path
from urllib.parse import urlparse
from domain_rule_engine import RuleIndex,load_domain_rules

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"
PENDING=ROOT/"reports/pending-gpt-review.json"
LEDGER=ROOT/"sources/gpt_domain_reviews.json"
FILTERED=ROOT/"reports/domain-filtered.json"
REPORT=ROOT/"reports/domain-filter.md"
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:[.][A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
COND_RE=re.compile(r"DOMAIN(?:-SUFFIX)?,([A-Za-z0-9.-]+)",re.I)

def fail(message): raise SystemExit("ERROR: "+message)

def main():
    pending=json.loads(PENDING.read_text(encoding="utf-8"))
    ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    reviewed={str(x.get("domain","")).lower() for x in ledger.get("reviews",[])}
    rules,conditional,ignored=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    config=CONFIG.read_text(encoding="utf-8")
    rule_block=config.split("[Rule]",1)[1].split("[Host]",1)[0]
    general=config.split("[General]",1)[1].split("[",1)[0]
    skip=[]
    for raw in general.splitlines():
        line=raw.strip()
        if line.startswith("skip-proxy="):
            skip += [x.strip().lower() for x in line.split("=",1)[1].split(",") if x.strip()]
    kept=[]; archived=[]; seen=set()
    for item in pending.get("candidates",[]):
        d=str(item.get("domain","")).lower().strip()
        if d in reviewed:
            kept.append(item); continue
        reason=None
        if not DOMAIN_RE.fullmatch(d):
            reason="Invalid domain syntax"
        elif d in seen:
            reason="Duplicate candidate"
        else:
            seen.add(d)
            if item.get("source_entry_type")=="suffix_candidate":
                reason="Source denotes suffix scope; exact DOMAIN-only automation cannot safely infer scope"
            else:
                winner=index.matches_host(d)
                if winner:
                    reason=f"Already governed by first-match {winner[0].policy} ({winner[0].kind} {winner[0].domain}, line {winner[0].line})"
                if not reason:
                    for _,raw in conditional:
                        for _,host in COND_RE.findall(raw):
                            host=host.lower().strip(".")
                            if d==host or d.endswith("."+host) or host.endswith("."+d):
                                reason="Overlaps existing conditional AND/OR/NOT domain rule"; break
                        if reason: break
                if not reason:
                    for entry in skip:
                        if entry.startswith("*."):
                            root=entry[2:]
                            if d==root or d.endswith("."+root):
                                reason="Matches General skip-proxy direct bypass "+entry; break
                        elif d==entry:
                            reason="Matches General skip-proxy direct bypass "+entry; break
                if not reason:
                    for raw in rule_block.splitlines():
                        line=raw.strip()
                        if line.startswith("DOMAIN-KEYWORD,"):
                            f=line.split(",",2)
                            if len(f)==3 and f[1].lower() in d:
                                reason="Matches existing DOMAIN-KEYWORD rule "+line; break
                        elif line.startswith("URL-REGEX,"):
                            f=line.rsplit(",",1)
                            if len(f)==2:
                                try: pattern=re.compile(f[0][len("URL-REGEX,"):])
                                except re.error: fail("Cannot safely evaluate existing URL-REGEX: "+line)
                                if pattern.search(d) or pattern.search("https://"+d+"/"):
                                    reason="Matches existing URL-REGEX rule "+line; break
        if reason:
            archived.append({**item,"filter_status":"FILTERED","filter_reason":reason})
        else:
            kept.append({**item,"filter_status":"READY_FOR_GPT"})
    # Preserve previous filtered history without duplicate domain records.
    old=[]
    if FILTERED.exists():
        old=json.loads(FILTERED.read_text(encoding="utf-8")).get("filtered",[])
    merged={x["domain"]:x for x in old}
    for x in archived: merged[x["domain"]]=x
    FILTERED.write_text(json.dumps({"schema_version":1,"filtered":sorted(merged.values(),key=lambda x:x["domain"])},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    PENDING.write_text(json.dumps({"schema_version":1,"updated_at":pending.get("updated_at"),"candidates":kept},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    ready=sum(1 for x in kept if x.get("domain","").lower() not in reviewed)
    report=["# Domain candidate filter","",f"Input candidates: {len(pending.get('candidates',[]))}",f"Ready for GPT: {ready}",f"Already in GPT ledger (retained for release gate): {len(kept)-ready}",f"Filtered and archived this run: {len(archived)}","",
            "Filtering checks syntax, duplicates, source scope, existing first-match DOMAIN/DOMAIN-SUFFIX rules, conditional rules, skip-proxy, DOMAIN-KEYWORD and URL-REGEX.",
            "Filtered candidates are retained in reports/domain-filtered.json for audit. No policy is inferred and ss.conf is read-only.",""]
    REPORT.write_text(chr(10).join(report),encoding="utf-8")
    print(chr(10).join(report))

if __name__=="__main__": main()
