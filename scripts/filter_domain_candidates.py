#!/usr/bin/env python3
"""Filter raw domain intake before placing candidates in the GPT review buffer."""
from __future__ import annotations
import json,re
from pathlib import Path
from domain_rule_engine import RuleIndex,load_domain_rules

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"
INTAKE=ROOT/"reports/domain-intake.json"
PENDING=ROOT/"reports/pending-gpt-review.json"
LEDGER=ROOT/"sources/gpt_domain_reviews.json"
FILTERED=ROOT/"reports/domain-filtered.json"
REPORT=ROOT/"reports/domain-filter.md"
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:[.][A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
MAX_RAW_PER_RUN=1000
MAX_PENDING=100
COND_RE=re.compile(r"DOMAIN(?:-SUFFIX)?,([A-Za-z0-9.-]+)",re.I)

def fail(message): raise SystemExit("ERROR: "+message)

def main():
    intake=json.loads(INTAKE.read_text(encoding="utf-8")) if INTAKE.exists() else {"candidates":[]}
    pending=json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else {"candidates":[]}
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
    kept={str(x.get("domain","")).lower():x for x in pending.get("candidates",[])}
    archived=[]
    raw_candidates=intake.get("candidates",[])
    remaining=[]
    processed=0
    for position,item in enumerate(raw_candidates):
        # Keep the GPT queue bounded and process the backlog in deterministic daily batches.
        if processed>=MAX_RAW_PER_RUN or len(kept)>=MAX_PENDING:
            remaining.extend(raw_candidates[position:])
            break
        processed+=1
        d=str(item.get("domain","")).lower().strip()
        reason=None
        if not DOMAIN_RE.fullmatch(d):
            reason="Invalid domain syntax"
        elif d in reviewed:
            reason="Already present in GPT review ledger"
        elif d in kept:
            reason="Duplicate already present in GPT review buffer"
        elif item.get("source_entry_type")=="suffix_candidate":
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
            kept[d]={**item,"filter_status":"READY_FOR_GPT"}
    old=[]
    if FILTERED.exists():
        old=json.loads(FILTERED.read_text(encoding="utf-8")).get("filtered",[])
    merged={x["domain"]:x for x in old}
    for x in archived: merged[x["domain"]]=x
    FILTERED.write_text(json.dumps({"schema_version":1,"filtered":sorted(merged.values(),key=lambda x:x["domain"])},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    PENDING.write_text(json.dumps({"schema_version":1,"updated_at":intake.get("updated_at",pending.get("updated_at")),"candidates":sorted(kept.values(),key=lambda x:x["domain"])},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    INTAKE.write_text(json.dumps({"schema_version":1,"updated_at":intake.get("updated_at"),"candidates":remaining},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
    report=["# Domain candidate filter","",f"Raw intake candidates at start: {len(raw_candidates)}",f"Raw candidates processed this run: {processed}",f"Remaining intake backlog: {len(remaining)}",f"Candidates retained in GPT buffer: {len(kept)}",f"Filtered and archived this run: {len(archived)}","",
            "Checks: syntax, duplicate/review-ledger status, exact-vs-suffix scope, existing first-match DOMAIN/DOMAIN-SUFFIX, conditional rules, skip-proxy, DOMAIN-KEYWORD and URL-REGEX.",
            f"Processing limits: at most {MAX_RAW_PER_RUN} raw candidates per run and {MAX_PENDING} candidates in the GPT buffer.",
            "Filtered candidates are retained in reports/domain-filtered.json. Unprocessed candidates remain in reports/domain-intake.json for later runs. ss.conf is read-only.",""]
    REPORT.write_text(chr(10).join(report),encoding="utf-8")
    print(chr(10).join(report))

if __name__=="__main__": main()
