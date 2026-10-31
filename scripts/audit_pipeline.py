#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys,tempfile
from pathlib import Path
from domain_rule_engine import RuleIndex,load_domain_rules
from deterministic_review import inspect
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"
POLICY=ROOT/"sources/policy.json"
LEDGER=ROOT/"sources/domain_reviews.json"
LEGACY=ROOT/"sources/legacy_managed_rules.json"
PUBLISHED=ROOT/"sources/published_domains.json"
PROTECTED=ROOT/"sources/protected_domains.json"
DNS_KEYS=("dns-server","fallback-dns-server","direct-dns-server","proxy-dns-server","dns-direct-system","dns-direct-fallback-proxy","hijack-dns")
START="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"
END="# END GPT-REVIEWED DOMAIN RULES (managed)"
L2="# === Layer 2: Explicit High-Priority Domain Rules & Exceptions (DOMAIN) ==="
L3="# === Layer 3 & Layer 4: Domestic (DIRECT) & International/Web3 (PROXY) Domain Sets (Length-Sorted Zero-Shadowing) ==="
def fail(msg): print("ERROR: "+msg,file=sys.stderr); raise SystemExit(1)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def main():
    text=CONFIG.read_text(encoding="utf-8")
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    legacy=json.loads(LEGACY.read_text(encoding="utf-8"))
    published=json.loads(PUBLISHED.read_text(encoding="utf-8"))
    protected=json.loads(PROTECTED.read_text(encoding="utf-8"))
    if any(text.count(s)!=1 for s in ("[General]","[Rule]","[Host]")): fail("required section count invalid")
    if not text.index("[General]")<text.index("[Rule]")<text.index("[Host]"): fail("section order invalid")
    lines=text.splitlines(keepends=True)
    a=[i for i,x in enumerate(lines) if x.strip()==START]
    b=[i for i,x in enumerate(lines) if x.strip()==END]
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed block markers invalid")
    if text.count(L2)!=1 or text.count(L3)!=1 or not text.index(L2)<text.index(START)<text.index(END)<text.index(L3): fail("managed block placement invalid")
    base="".join(lines[:a[0]]+lines[b[0]+1:])
    if blob(base.encode("utf-8"))!=policy["canonical_config"]["approved_git_blob_sha"]: fail("unmanaged config bytes differ from approved baseline")
    general=text.split("[General]",1)[1].split("[Rule]",1)[0]
    values={}
    for raw in general.splitlines():
        row=raw.strip()
        if row and not row.startswith("#") and "=" in row:
            k,v=(z.strip() for z in row.split("=",1)); values.setdefault(k,[]).append(v)
    for key in DNS_KEYS:
        if values.get(key)!=[policy["dns_invariants"].get(key)]: fail("DNS invariant changed: "+key)
    if policy.get("allowed_policy_outputs")!=["DIRECT","PROXY","REJECT"]: fail("allowed policy outputs changed")
    release=policy.get("release_policy",{})
    if release.get("gpt_review_required") is not False or release.get("automatic_policy_inference") is not True: fail("deterministic no-GPT policy flags invalid")
    if float(release.get("minimum_confidence",0))!=0.26: fail("confidence threshold must remain 0.26")
    if int(release.get("minimum_independent_evidence_sources",0))!=1: fail("independent source threshold invalid")
    block=text.split("[Rule]",1)[1].split("[Host]",1)[0].splitlines()
    s=next(i for i,x in enumerate(block) if x.strip()==START)
    e=next(i for i,x in enumerate(block) if x.strip()==END)
    imported=[x.strip() for x in block[s+1:e] if x.strip() and not x.strip().startswith("#")]
    seen=set()
    for line in imported:
        f=[x.strip() for x in line.split(",")]
        if len(f)!=3 or f[0]!="DOMAIN" or f[2] not in {"DIRECT","PROXY","REJECT"}: fail("invalid managed exact-domain rule: "+line)
        if f[1] in seen: fail("duplicate managed domain: "+f[1])
        seen.add(f[1])
    legacy_rules=set(legacy.get("rules",[]))
    if not legacy_rules.issubset(set(imported)): fail("one or more pre-existing managed rules were removed")
    published_rows=published.get("published",[])
    published_map={}
    for row in published_rows:
        d=row.get("domain","")
        rule="DOMAIN,"+d+","+str(row.get("policy","")).upper()
        if d in published_map: fail("duplicate publication-history domain: "+d)
        if row.get("policy") not in {"DIRECT","PROXY","REJECT"}: fail("invalid publication-history policy: "+d)
        if float(row.get("confidence",0))<0.26: fail("publication-history confidence below threshold: "+d)
        if len({x.get("source_id") for x in row.get("source_evidence",[])})<1: fail("publication-history evidence below minimum: "+d)
        published_map[d]=rule
    allowed=set(legacy_rules)|set(published_map.values())
    if not set(imported).issubset(allowed): fail("managed rule lacks legacy or append-only publication provenance")
    if not set(published_map.values()).issubset(set(imported)): fail("publication history contains a rule missing from ss.conf")
    approved={x["domain"]:"DOMAIN,"+x["domain"]+","+x["policy"] for x in ledger.get("reviews",[]) if x.get("status")=="APPROVED"}
    if len(approved)!=len([x for x in ledger.get("reviews",[]) if x.get("status")=="APPROVED"]): fail("duplicate approved domains in ledger")
    for domain,rule in approved.items():
        if rule not in imported: fail("approved rule not published: "+domain)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".conf",delete=False) as f:
        f.write(base); name=f.name
    try:
        rules,conditional,ignored=load_domain_rules(Path(name))
    finally:
        Path(name).unlink(missing_ok=True)
    index=RuleIndex(rules)
    for domain in published_map:
        status,reason=inspect(domain,index,conditional,base,protected)
        if status is not None: fail("published rule fails current duplicate/conflict/risk recheck: "+domain+" ("+str(status)+": "+str(reason)+")")
    print("PASS: canonical baseline, deterministic ledger, publication provenance, original-rule protection and 7 DNS invariants")
    print("Managed exact-domain rules: "+str(len(imported))+" (legacy preserved: "+str(len(legacy_rules))+", auto-published: "+str(len(published_map))+")")
    print("GPT ledger is not read; DNS, nodes, MITM and unmanaged config bytes remain protected.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: fail(str(e))
