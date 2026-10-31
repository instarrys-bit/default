#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, sys, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/"sources/domain_sources.json"
BUFFER=ROOT/"data/domain_candidates.json"
OUTPUT=ROOT/"data/candidates.json"
MAX_BYTES=20_000_000
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Shadowrocket-Deterministic-Audit/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        if r.status!=200 or r.geturl().split(":",1)[0]!="https":
            raise ValueError("unexpected source response: "+url)
        data=r.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES: raise ValueError("source exceeds byte limit: "+url)
    return data
def parse_domain_list(data,allow_leading_dot=False):
    result=set()
    for number,raw in enumerate(data.decode("utf-8-sig").splitlines(),1):
        value=raw.strip()
        if not value or value.startswith(("#","!")): continue
        if allow_leading_dot and value.startswith("."): value=value[1:]
        value=value.lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(value):
            raise ValueError(f"unsupported/non-domain line {number}: {raw[:120]!r}")
        result.add(value)
    return result
def main():
    cfg=json.loads(SOURCES.read_text(encoding="utf-8"))
    buf=json.loads(BUFFER.read_text(encoding="utf-8"))
    candidates=buf.get("candidates",[])
    by_id={x["id"]:x for x in cfg["sources"]}
    primary=by_id["sr-adblock-domain-lite"]
    secondary=by_id["hagezi-domains-pro"]
    primary_bytes=fetch(primary["url"])
    primary_hash=hashlib.sha256(primary_bytes).hexdigest()
    if primary_hash!=primary["expected_sha256"]:
        raise SystemExit("ERROR: primary source drift; candidate baseline must be refreshed and re-audited")
    primary_domains=parse_domain_list(primary_bytes,allow_leading_dot=True)
    if len(primary_domains)!=int(primary["expected_entries"]):
        raise SystemExit("ERROR: primary source entry count mismatch")
    secondary_bytes=fetch(secondary["url"])
    secondary_hash=hashlib.sha256(secondary_bytes).hexdigest()
    secondary_domains=parse_domain_list(secondary_bytes)
    rows=[]
    for item in candidates:
        domain=str(item.get("domain","")).lower().rstrip(".")
        if not DOMAIN_RE.fullmatch(domain): raise ValueError("invalid candidate domain: "+domain)
        if item.get("source_id")!=primary["id"]: raise ValueError("candidate source id mismatch: "+domain)
        if item.get("source_sha256")!=primary_hash: raise ValueError("candidate source hash mismatch: "+domain)
        if domain not in primary_domains: raise ValueError("candidate no longer exists in primary source: "+domain)
        evidence=[{"source_id":primary["id"],"publisher":primary["publisher"],"url":primary["url"],"sha256":primary_hash}]
        if domain in secondary_domains:
            evidence.append({"source_id":secondary["id"],"publisher":secondary["publisher"],"url":secondary["url"],"sha256":secondary_hash})
        rows.append({"domain":domain,"classification":"REJECT","evidence":evidence,"first_seen":item.get("first_seen")})
    rows.sort(key=lambda x:x["domain"])
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps({"schema_version":1,"collected_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"sources":[{"id":primary["id"],"sha256":primary_hash,"entries":len(primary_domains)},{"id":secondary["id"],"sha256":secondary_hash,"entries":len(secondary_domains)}],"candidates":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Collected {len(rows)} candidates; {sum(len(x['evidence'])>=2 for x in rows)} independently corroborated by both sources.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
