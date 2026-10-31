#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"; POLICY=ROOT/"sources/policy.json"; LEDGER=ROOT/"sources/gpt_domain_reviews.json"
START="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"; END="# END GPT-REVIEWED DOMAIN RULES (managed)"
DNS_KEYS=("dns-server","fallback-dns-server","direct-dns-server","proxy-dns-server","dns-direct-system","dns-direct-fallback-proxy","hijack-dns")
L2="# === Layer 2: Explicit High-Priority Domain Rules & Exceptions (DOMAIN) ==="
L3="# === Layer 3 & Layer 4: Domestic (DIRECT) & International/Web3 (PROXY) Domain Sets (Length-Sorted Zero-Shadowing) ==="
def fail(m): print("ERROR: "+m,file=sys.stderr); raise SystemExit(1)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def main():
    text=CONFIG.read_text(encoding="utf-8"); p=json.loads(POLICY.read_text(encoding="utf-8"))
    if any(text.count(s)!=1 for s in ("[General]","[Rule]","[Host]")): fail("required section count invalid")
    if not text.index("[General]")<text.index("[Rule]")<text.index("[Host]"): fail("section order invalid")
    lines=text.splitlines(keepends=True)
    a=[i for i,x in enumerate(lines) if x.strip()==START]; b=[i for i,x in enumerate(lines) if x.strip()==END]
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed import markers invalid")
    if text.count(L2)!=1 or text.count(L3)!=1 or not text.index(L2)<text.index(START)<text.index(END)<text.index(L3):
        fail("managed block must remain after explicit Layer 2 and before Layer 3")
    base="".join(lines[:a[0]]+lines[b[0]+1:])
    actual=blob(base.encode("utf-8")); expected=p["canonical_config"]["approved_git_blob_sha"]
    if actual!=expected: fail(f"unmanaged config changed: expected {expected}, got {actual}")
    general=text.split("[General]",1)[1].split("[",1)[0]; values={}
    for raw in general.splitlines():
        line=raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k,v=(z.strip() for z in line.split("=",1)); values.setdefault(k,[]).append(v)
    for k in DNS_KEYS:
        if values.get(k)!=[p["dns_invariants"].get(k)]: fail("DNS invariant changed: "+k)
    if p.get("allowed_policy_outputs")!=["DIRECT","PROXY","REJECT"]: fail("allowed policies changed")
    rel=p.get("release_policy",{})
    if rel.get("automatic_config_rewrite") is not True or rel.get("automatic_policy_inference") is not False or rel.get("gpt_review_required") is not True:
        fail("GPT-reviewed publication policy flags invalid")
    rule=text.split("[Rule]",1)[1].split("[Host]",1)[0].splitlines()
    start=next(i for i,x in enumerate(rule) if x.strip()==START); end=next(i for i,x in enumerate(rule) if x.strip()==END)
    imported=[x.strip() for x in rule[start+1:end] if x.strip() and not x.strip().startswith("#")]
    ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    approved={x["domain"]:x for x in ledger.get("reviews",[]) if str(x.get("status","")).upper()=="APPROVED"}
    seen=set()
    for line in imported:
        f=[x.strip() for x in line.split(",")]
        if len(f)!=3 or f[0]!="DOMAIN" or f[2] not in {"DIRECT","PROXY","REJECT"}: fail("invalid managed rule: "+line)
        if f[1] in seen: fail("duplicate managed domain: "+f[1])
        seen.add(f[1])
        item=approved.get(f[1])
        if not item or str(item.get("policy","")).upper()!=f[2]: fail("managed rule lacks matching GPT approval: "+f[1])
    print("PASS: canonical baseline, GPT approval ledger, managed rules and 7 DNS invariants")
    print("Managed exact domain rules: "+str(len(imported)))
    print("Unmanaged config bytes preserved; DNS, nodes, MITM and URL Rewrite unchanged.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: fail(str(e))
