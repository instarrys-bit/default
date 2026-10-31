#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,sys,urllib.request
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/"sources/domain_sources.json"
BUFFER=ROOT/"data/domain_candidates.json"
SNAPSHOT=ROOT/"data/primary_snapshot.txt"
REVIEWS=ROOT/"sources/domain_reviews.json"
OUTPUT=ROOT/"data/candidates.json"
MAX_BYTES=30_000_000
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Shadowrocket-Deterministic-Audit/1.1"})
    with urllib.request.urlopen(req,timeout=90) as r:
        final=urlparse(r.geturl())
        if r.status!=200 or final.scheme!="https" or final.hostname!="raw.githubusercontent.com":
            raise ValueError("unexpected source response: "+r.geturl())
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
def parse_adblock(data):
    result=set()
    rule=re.compile(r"^\|\|([a-z0-9.-]+)\^")
    for raw in data.decode("utf-8-sig").splitlines():
        value=raw.strip()
        if not value or value.startswith(("!","[","@@")): continue
        match=rule.match(value.lower())
        if not match: continue
        domain=match.group(1).rstrip(".")
        if DOMAIN_RE.fullmatch(domain): result.add(domain)
    if not result: raise ValueError("secondary Adblock source yielded no domain rules")
    return result
def main():
    cfg=json.loads(SOURCES.read_text(encoding="utf-8"))
    buf=json.loads(BUFFER.read_text(encoding="utf-8"))
    by_id={x["id"]:x for x in cfg["sources"]}
    primary=by_id["sr-adblock-domain-lite"]
    secondary=by_id["hagezi-domains-pro"]
    primary_bytes=fetch(primary["url"])
    primary_hash=hashlib.sha256(primary_bytes).hexdigest()
    primary_domains=parse_domain_list(primary_bytes,allow_leading_dot=True)
    minimum=int(primary.get("minimum_entries",50000))
    if len(primary_domains)<minimum: raise ValueError("primary source unexpectedly small or truncated")
    secondary_bytes=fetch(secondary["url"])
    secondary_hash=hashlib.sha256(secondary_bytes).hexdigest()
    secondary_domains=parse_adblock(secondary_bytes)
    if SNAPSHOT.exists():
        previous={x.strip().lower() for x in SNAPSHOT.read_text(encoding="utf-8").splitlines() if x.strip()}
    else:
        previous=set(primary_domains)
    discovered=primary_domains-previous
    queue={x["domain"]:x for x in buf.get("candidates",[])}
    now=datetime.now(timezone.utc).isoformat()
    for domain in sorted(discovered):
        if domain not in queue:
            queue[domain]={"domain":domain,"source_id":primary["id"],"source_sha256":primary_hash,"first_seen":now,"source_entry_type":"new_source_delta"}
    rows=[]
    for domain,item in sorted(queue.items()):
        if not DOMAIN_RE.fullmatch(domain): raise ValueError("invalid candidate domain: "+domain)
        evidence=[]
        evidence.append({"source_id":primary["id"],"publisher":primary["publisher"],"url":primary["url"],"sha256":primary_hash,"currently_listed":domain in primary_domains})
        if any(domain==x or domain.endswith("."+x) for x in secondary_domains):
            evidence.append({"source_id":secondary["id"],"publisher":secondary["publisher"],"url":secondary["url"],"sha256":secondary_hash})
        item["source_sha256"]=primary_hash
        rows.append({"domain":domain,"classification":"REJECT","evidence":evidence,"first_seen":item.get("first_seen")})
    BUFFER.write_text(json.dumps({"schema_version":1,"updated_at":now,"candidates":list(queue.values())},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    SNAPSHOT.parent.mkdir(parents=True,exist_ok=True)
    SNAPSHOT.write_text("\n".join(sorted(primary_domains))+"\n",encoding="utf-8")
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps({"schema_version":1,"collected_at":now,"new_primary_domains":len(discovered),"sources":[{"id":primary["id"],"sha256":primary_hash,"entries":len(primary_domains)},{"id":secondary["id"],"sha256":secondary_hash,"entries":len(secondary_domains)}],"candidates":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Primary source domains: {len(primary_domains)}; newly discovered: {len(discovered)}; queued candidates: {len(rows)}; corroborated by both sources: {sum(len(x['evidence'])>=2 for x in rows)}.")
if __name__=="__main__":
    try: main()
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as e: print("ERROR: "+str(e),file=sys.stderr); raise SystemExit(1)
