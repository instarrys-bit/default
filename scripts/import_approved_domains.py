#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
from domain_rule_engine import RuleIndex,load_domain_rules
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"
POLICY=ROOT/"sources/policy.json"
REVIEWS=ROOT/"sources/domain_reviews.json"
REPORT=ROOT/"reports/domain-publication.md"
START="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"
END="# END GPT-REVIEWED DOMAIN RULES (managed)"
LAYER3="# === Layer 3 & Layer 4: Domestic (DIRECT) & International/Web3 (PROXY) Domain Sets (Length-Sorted Zero-Shadowing) ==="
def fail(msg): raise SystemExit("ERROR: "+msg)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def strip_block(text):
    lines=text.splitlines(keepends=True)
    a=[i for i,x in enumerate(lines) if x.strip()==START]
    b=[i for i,x in enumerate(lines) if x.strip()==END]
    if not a and not b: return text
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed block markers malformed")
    return "".join(lines[:a[0]]+lines[b[0]+1:])
def main():
    check="--check" in sys.argv
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    ledger=json.loads(REVIEWS.read_text(encoding="utf-8"))
    original=CONFIG.read_text(encoding="utf-8")
    base=strip_block(original)
    expected=policy["canonical_config"]["approved_git_blob_sha"]
    if blob(base.encode("utf-8"))!=expected: fail("unmanaged config differs from approved canonical baseline")
    if original.count(START)!=1 or original.count(END)!=1: fail("managed markers missing or duplicated")
    entries=ledger.get("reviews",[])
    if not isinstance(entries,list): fail("deterministic review ledger schema invalid")
    approved=[]
    for item in entries:
        if str(item.get("status","")).upper()!="APPROVED": continue
        domain=str(item.get("domain","")).lower()
        pol=str(item.get("policy","")).upper()
        if pol not in {"DIRECT","PROXY","REJECT"}: fail("invalid policy for "+domain)
        if float(item.get("confidence",0))<float(policy["release_policy"]["minimum_confidence"]): fail("confidence below threshold for "+domain)
        if item.get("duplicate_check")!="PASS" or item.get("conflict_check")!="PASS" or item.get("risk_check")!="PASS": fail("approval missing mandatory audit passes: "+domain)
        if len({x.get("source_id") for x in item.get("evidence",[])})<int(policy["release_policy"]["minimum_independent_evidence_sources"]): fail("insufficient independent evidence for "+domain)
        approved.append("DOMAIN,"+domain+","+pol)
    existing_lines=original.splitlines()
    a=next(i for i,x in enumerate(existing_lines) if x.strip()==START)
    b=next(i for i,x in enumerate(existing_lines) if x.strip()==END)
    old=[x.strip() for x in existing_lines[a+1:b] if x.strip() and not x.strip().startswith("#")]
    old_domains={}
    for line in old:
        f=[x.strip() for x in line.split(",")]
        if len(f)!=3 or f[0]!="DOMAIN" or f[2] not in {"DIRECT","PROXY","REJECT"}: fail("invalid existing managed rule: "+line)
        if f[1] in old_domains and old_domains[f[1]]!=f[2]: fail("managed block contains policy conflict: "+f[1])
        old_domains[f[1]]=f[2]
    rules,conditional,ignored=load_domain_rules(CONFIG)
    index=RuleIndex(rules)
    additions=[]
    for line in sorted(set(approved)):
        _,domain,pol=line.split(",")
        if domain in old_domains:
            if old_domains[domain]!=pol: fail("new approval conflicts with existing managed rule: "+domain)
            continue
        hits=index.matches_host(domain)
        if hits:
            fail("approved candidate is already governed by original first-match rule: "+domain)
        for _,raw in conditional:
            if domain in raw.lower():
                fail("approved candidate intersects conditional rule: "+domain)
        additions.append(line)
    merged=sorted(set(old+additions))
    block=START+"\n"+("\n".join(merged)+"\n" if merged else "")+END+"\n"
    if original.count(START)!=1 or original.count(END)!=1: fail("managed block markers invalid")
    lines=original.splitlines(keepends=True)
    a=next(i for i,x in enumerate(lines) if x.strip()==START)
    b=next(i for i,x in enumerate(lines) if x.strip()==END)
    updated="".join(lines[:a])+block+"".join(lines[b+1:])
    if strip_block(updated)!=base: fail("unmanaged config bytes changed")
    if check:
        if updated!=original: fail("managed config is not synchronized with deterministic approvals")
        print("PASS: deterministic approvals synchronized; "+str(len(merged))+" managed exact-domain rules")
        return
    CONFIG.write_text(updated,encoding="utf-8")
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    counts=ledger.get("counts",{})
    REPORT.write_text("# Deterministic domain publication\n\n"+
      "- Review engine: deterministic-domain-audit/1.0\n"+
      "- Candidates reviewed: "+str(len(entries))+"\n"+
      "- New rules added: "+str(len(additions))+"\n"+
      "- Existing managed rules preserved: "+str(len(old))+"\n"+
      "- Review outcomes: "+json.dumps(counts,ensure_ascii=False,sort_keys=True)+"\n\n"+
      "Only independently corroborated exact-host REJECT candidates are eligible. Exact/suffix duplicates, conflicts, conditional overlaps and protected critical-function hosts are not published.\n"+
      "DNS, nodes, MITM, original rules and all bytes outside the managed block are protected.\n",encoding="utf-8")
    print("Added "+str(len(additions))+" new rules; preserved "+str(len(old))+" existing managed rules.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
