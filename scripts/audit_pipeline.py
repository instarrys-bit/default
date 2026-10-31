#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"; POLICY=ROOT/"sources/policy.json"; LEDGER=ROOT/"sources/gpt_domain_reviews.json"
START="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"; END="# END GPT-REVIEWED DOMAIN RULES (managed)"
DNS_KEYS=("dns-server","fallback-dns-server","direct-dns-server","proxy-dns-server","dns-direct-system","dns-direct-fallback-proxy","hijack-dns")
L2="# === Layer 2: Explicit High-Priority Domain Rules & Exceptions (DOMAIN) ==="
L3="# === Layer 3 & Layer 4: Domestic (DIRECT) & International/Web3 (PROXY) Domain Sets (Length-Sorted Zero-Shadowing) ==="
SEARCH_HOSTS={"google.com","bing.com","duckduckgo.com","search.yahoo.com","yandex.com"}
def fail(m): print("ERROR: "+m,file=sys.stderr); raise SystemExit(1)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def main():
    text=CONFIG.read_text(encoding="utf-8"); p=json.loads(POLICY.read_text(encoding="utf-8")); ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    if any(text.count(s)!=1 for s in ("[General]","[Rule]","[Host]")): fail("required section count invalid")
    if not text.index("[General]")<text.index("[Rule]")<text.index("[Host]"): fail("section order invalid")
    lines=text.splitlines(keepends=True); a=[i for i,x in enumerate(lines) if x.strip()==START]; b=[i for i,x in enumerate(lines) if x.strip()==END]
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed import markers invalid")
    if text.count(L2)!=1 or text.count(L3)!=1 or not text.index(L2)<text.index(START)<text.index(END)<text.index(L3): fail("managed block position invalid")
    base="".join(lines[:a[0]]+lines[b[0]+1:])
    if blob(base.encode("utf-8"))!=p["canonical_config"]["approved_git_blob_sha"]: fail("unmanaged config bytes changed")
    general=text.split("[General]",1)[1].split("[",1)[0]; values={}
    for raw in general.splitlines():
        row=raw.strip()
        if row and not row.startswith("#") and "=" in row:
            k,v=(z.strip() for z in row.split("=",1)); values.setdefault(k,[]).append(v)
    for k in DNS_KEYS:
        if values.get(k)!=[p["dns_invariants"].get(k)]: fail("DNS invariant changed: "+k)
    if p.get("allowed_policy_outputs")!=["DIRECT","PROXY","REJECT"]: fail("allowed policy set changed")
    release=p.get("release_policy",{})
    if release.get("automatic_config_rewrite") is not True or release.get("automatic_policy_inference") is not False or release.get("gpt_review_required") is not True: fail("publication policy flags invalid")
    approved={x["domain"]:x for x in ledger.get("reviews",[]) if str(x.get("status","")).upper()=="APPROVED"}
    rules=text.split("[Rule]",1)[1].split("[Host]",1)[0].splitlines()
    s=next(i for i,x in enumerate(rules) if x.strip()==START); e=next(i for i,x in enumerate(rules) if x.strip()==END)
    imported=[x.strip() for x in rules[s+1:e] if x.strip() and not x.strip().startswith("#")]
    min_sources=int(release.get("minimum_independent_evidence_sources",2)); min_conf=float(release.get("minimum_confidence",0.90))
    seen=set()
    for line in imported:
        f=[x.strip() for x in line.split(",")]
        if len(f)!=3 or f[0]!="DOMAIN" or f[2] not in {"DIRECT","PROXY","REJECT"}: fail("invalid managed rule: "+line)
        d=f[1]
        if d in seen: fail("duplicate managed domain: "+d)
        seen.add(d)
        item=approved.get(d)
        if not item or str(item.get("policy","")).upper()!=f[2]: fail("managed rule lacks matching GPT approval: "+d)
        if not isinstance(item.get("confidence"),(int,float)) or item["confidence"]<min_conf: fail("GPT approval confidence below threshold: "+d)
        ev=item.get("evidence",[])
        hosts=set(); publishers=set()
        if not isinstance(ev,list) or len(ev)<min_sources: fail("insufficient evidence count: "+d)
        for x in ev:
            url=str(x.get("url","")); host=(urlparse(url).hostname or "").lower()
            pub=str(x.get("publisher","")).strip().lower()
            if not url.startswith("https://") or not host or any(host==z or host.endswith("."+z) for z in SEARCH_HOSTS): fail("invalid evidence URL: "+d)
            if not pub or not str(x.get("supports","")).strip(): fail("evidence metadata missing: "+d)
            hosts.add(host); publishers.add(pub)
        if len(hosts)<min_sources or len(publishers)<min_sources: fail("evidence is not independent: "+d)
        if not str(item.get("reason","")).strip() or not str(item.get("reviewed_at","")).strip(): fail("review rationale/date missing: "+d)
    print("PASS: canonical baseline, GPT evidence, managed rules and 7 DNS invariants")
    print("Managed exact domain rules: "+str(len(imported)))
    print("Unmanaged config bytes preserved; DNS, nodes, MITM and URL Rewrite unchanged.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: fail(str(e))
