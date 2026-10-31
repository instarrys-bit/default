#!/usr/bin/env python3
from __future__ import annotations
import base64,hashlib,json,re,sys,urllib.request,zlib
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/"sources/policy.json"; STATE=ROOT/"reports/domain-source-bloom.json"
INTAKE=ROOT/"reports/domain-intake.json"; REPORT=ROOT/"reports/domain-capture.md"
BITS=4_000_000; HASHES=10; MAX_BYTES=8_000_000
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
def fail(m): raise SystemExit("ERROR: "+m)
def indices(d):
    h=hashlib.sha256(d.encode("ascii")).digest(); a=int.from_bytes(h[:8],"big"); b=int.from_bytes(h[8:16],"big")|1
    for i in range(HASHES): yield (a+i*b+i*i)%BITS
def add(bits,d):
    for i in indices(d): bits[i>>3]|=1<<(i&7)
def has(bits,d): return all(bits[i>>3]&(1<<(i&7)) for i in indices(d))
def main():
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    src=[x for x in p.get("external_sources",[]) if x.get("enabled") and x.get("capture_enabled")]
    if len(src)!=1: fail("exactly one capture source must be enabled")
    src=src[0]; u=urlparse(src["url"])
    if u.scheme!="https" or u.hostname!="raw.githubusercontent.com": fail("source must be HTTPS raw.githubusercontent.com")
    req=urllib.request.Request(src["url"],headers={"User-Agent":"Shadowrocket-Domain-Capture/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            final=urlparse(r.geturl())
            if r.status!=200 or final.scheme!="https" or final.hostname!="raw.githubusercontent.com": fail("unexpected redirect or response")
            data=r.read(MAX_BYTES+1)
    except Exception as e: fail("download failed: "+str(e))
    if len(data)>MAX_BYTES: fail("source exceeds 8 MB")
    try: lines=data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as e: fail("source is not UTF-8: "+str(e))
    found={}
    for n,raw in enumerate(lines,1):
        v=raw.strip()
        if not v or v.startswith("#"): continue
        if v!=raw or any(c.isspace() for c in v): fail(f"unexpected whitespace at line {n}")
        suffix=v.startswith("."); d=(v[1:] if suffix else v).lower()
        if not DOMAIN_RE.fullmatch(d): fail(f"invalid domain at line {n}: {raw!r}")
        if d in found: fail("duplicate domain: "+d)
        found[d]="suffix_candidate" if suffix else "exact_candidate"
    if not 1000<=len(found)<=200000: fail("source entry count outside safety bounds")
    sha=hashlib.sha256(data).hexdigest(); now=datetime.now(timezone.utc).isoformat()
    first=not STATE.exists()
    if first:
        bits=bytearray((BITS+7)//8)
        new=found.copy()
        for d in found: add(bits,d)
        baseline_imported=True
    else:
        st=json.loads(STATE.read_text(encoding="utf-8"))
        if st.get("schema_version")!=1 or st.get("bits")!=BITS or st.get("hashes")!=HASHES: fail("Bloom state schema mismatch")
        bits=bytearray(zlib.decompress(base64.b64decode(st["data"])))
        if len(bits)!=(BITS+7)//8: fail("Bloom state size mismatch")
        baseline_imported=st.get("baseline_imported") is True
        if not baseline_imported:
            # One-time migration: queue the already-baselined source entries instead of silently skipping them.
            new=found.copy()
        else:
            new={d:t for d,t in found.items() if not has(bits,d)}
        for d in found: add(bits,d)
        if baseline_imported and sha==st.get("source_sha256") and not new:
            print("No source change or new domains; no repository write needed.")
            return
    pending={}
    if INTAKE.exists():
        old=json.loads(INTAKE.read_text(encoding="utf-8")); pending={x["domain"]:x for x in old.get("candidates",[])}
    for d,t in new.items():
        pending.setdefault(d,{"domain":d,"source_entry_type":t,"first_seen":now,"source_id":src["id"],"source_sha256":sha})
    INTAKE.parent.mkdir(parents=True,exist_ok=True); STATE.parent.mkdir(parents=True,exist_ok=True)
    state={"schema_version":1,"bits":BITS,"hashes":HASHES,"source_id":src["id"],"source_sha256":sha,
           "entry_count":len(found),"baseline_imported":True,"updated_at":now,"data":base64.b64encode(zlib.compress(bytes(bits),9)).decode("ascii")}
    INTAKE.write_text(json.dumps({"schema_version":1,"updated_at":now,"candidates":sorted(pending.values(),key=lambda x:x["domain"])},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    STATE.write_text(json.dumps(state,separators=(",",":"))+"\n",encoding="utf-8")
    report=["# Domain source capture","",f"Source: {src['url']}",f"SHA-256: {sha}",f"Current entries: {len(found)}",
            f"New candidates detected: {len(new)}",f"Raw intake candidates awaiting filter: {len(pending)}",
            "Initial baseline migration: "+("all current source entries queued for first-pass filtering" if not baseline_imported or first else "already completed"),"",
            "Only domain strings are captured. Upstream policy, scripts, modules, DNS, MITM and rewrite directives are never imported.",
            "A compact Bloom filter tracks prior domains without storing a plain copy of the source list. Its false-positive probability is negligible; it has no false negatives.",
            "Source removals never delete existing rules automatically. Candidates are staged in domain-intake.json; no GPT buffer or config changes occur during capture.",""]
    REPORT.write_text("\n".join(report),encoding="utf-8"); print("\n".join(report))
if __name__=="__main__": main()
