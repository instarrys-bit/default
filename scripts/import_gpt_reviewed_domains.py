#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path
from urllib.parse import urlparse
from domain_rule_engine import RuleIndex,analyze_candidate,load_domain_rules
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"shadowrocket/ss.conf"; POLICY=ROOT/"sources/policy.json"
REVIEWS=ROOT/"sources/gpt_domain_reviews.json"; PENDING=ROOT/"reports/pending-gpt-review.json"
REPORT=ROOT/"reports/gpt-domain-publication.md"
START="# BEGIN GPT-REVIEWED DOMAIN RULES (managed)"
END="# END GPT-REVIEWED DOMAIN RULES (managed)"
LAYER3="# === Layer 3 & Layer 4: Domestic (DIRECT) & International/Web3 (PROXY) Domain Sets (Length-Sorted Zero-Shadowing) ==="
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
COND_RE=re.compile(r"DOMAIN(-SUFFIX)?,([A-Za-z0-9.-]+)",re.I)
SEARCH_HOSTS={"google.com","bing.com","duckduckgo.com","search.yahoo.com","yandex.com"}
def fail(m): raise SystemExit("ERROR: "+m)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def strip_block(text):
    lines=text.splitlines(keepends=True); a=[i for i,x in enumerate(lines) if x.strip()==START]; b=[i for i,x in enumerate(lines) if x.strip()==END]
    if not a and not b: return text
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed block markers malformed")
    return "".join(lines[:a[0]]+lines[b[0]+1:])
def conditional_overlap(domain,conditional):
    for _,raw in conditional:
        for d in COND_RE.findall(raw):
            d=d.lower().strip(".")
            if domain==d or domain.endswith("."+d) or d.endswith("."+domain): return True
    return False
def load_rules_from_text(content):
    import tempfile
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".conf",delete=False) as f:
        f.write(content); name=f.name
    try: return load_domain_rules(Path(name))
    finally: Path(name).unlink(missing_ok=True)
def parse_general(text,key):
    block=text.split("[General]",1)[1].split("[",1)[0]
    for raw in block.splitlines():
        line=raw.strip()
        if line.startswith(key+"="): return [x.strip().lower() for x in line.split("=",1)[1].split(",") if x.strip()]
    return []
def other_rule_match(domain,base,policy):
    skip=parse_general(base,"skip-proxy")
    for item in skip:
        if "/" in item or ":" in item: continue
        if item.startswith("*."):
            root=item[2:]
            if domain==root or domain.endswith("."+root): return "Matches skip-proxy direct-bypass entry "+item
        elif domain==item: return "Matches skip-proxy direct-bypass entry "+item
    rule_block=base.split("[Rule]",1)[1].split("[Host]",1)[0]
    for raw in rule_block.splitlines():
        line=raw.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("DOMAIN-KEYWORD,"):
            fields=line.split(",",2)
            if len(fields)==3 and fields[1].lower() in domain:
                return "Matches existing DOMAIN-KEYWORD rule with policy "+fields[2].strip().upper()
        if line.startswith("URL-REGEX,"):
            fields=line.rsplit(",",1)
            if len(fields)==2:
                try: pattern=re.compile(fields[0][len("URL-REGEX,"):])
                except re.error: fail("existing URL-REGEX cannot be safely evaluated: "+line)
                if pattern.search(domain) or pattern.search("https://"+domain+"/"):
                    return "Matches existing URL-REGEX rule with policy "+fields[1].strip().upper()
    return None
def validate_evidence(d,evidence,min_sources):
    if not isinstance(evidence,list) or len(evidence)<min_sources: fail("too few evidence sources for "+d)
    hosts=set(); publishers=set()
    for ev in evidence:
        url=str(ev.get("url","")).strip()
        if not url.startswith("https://"): fail("non-HTTPS evidence URL for "+d)
        parsed=urlparse(url); host=(parsed.hostname or "").lower()
        if not host or any(host==x or host.endswith("."+x) for x in SEARCH_HOSTS): fail("search-result pages are not evidence for "+d)
        publisher=str(ev.get("publisher","")).strip().lower(); supports=str(ev.get("supports","")).strip()
        if not publisher or not supports: fail("publisher/supporting claim missing for "+d)
        hosts.add(host); publishers.add(publisher)
    if len(hosts)<min_sources or len(publishers)<min_sources: fail("evidence publishers and hosts are not sufficiently independent for "+d)
def main():
    check="--check" in sys.argv
    policy=json.loads(POLICY.read_text(encoding="utf-8")); release=policy["release_policy"]
    min_sources=int(release.get("minimum_independent_evidence_sources",2)); min_conf=float(release.get("minimum_confidence",0.90))
    original=CONFIG.read_text(encoding="utf-8"); base=strip_block(original)
    if blob(base.encode("utf-8"))!=policy["canonical_config"]["approved_git_blob_sha"]: fail("config outside managed block differs from approved baseline")
    if not REVIEWS.exists() or not PENDING.exists(): fail("review ledger or pending queue missing")
    ledger=json.loads(REVIEWS.read_text(encoding="utf-8")); pending=json.loads(PENDING.read_text(encoding="utf-8"))
    queue={x["domain"]:x for x in pending.get("candidates",[])}; entries=ledger.get("reviews",[])
    if not isinstance(entries,list): fail("review ledger schema invalid")
    review_map={}
    for item in entries:
        d=str(item.get("domain","")).lower().strip()
        if not DOMAIN_RE.fullmatch(d) or d in review_map: fail("invalid or duplicate review domain: "+d)
        review_map[d]=item
    rules,conditional,ignored=load_rules_from_text(base); index=RuleIndex(rules)
    old_managed=[]
    if START in original:
        ll=original.splitlines(); a=next(i for i,x in enumerate(ll) if x.strip()==START); b=next(i for i,x in enumerate(ll) if x.strip()==END)
        old_managed=[x.strip() for x in ll[a+1:b] if x.strip() and not x.strip().startswith("#")]
    approved=[]; quarantined=[]; reviewed=set()
    for d,item in sorted(review_map.items()):
        if d not in queue: continue
        status=str(item.get("status","")).upper()
        if status not in {"APPROVED","REVIEW"}: fail("unsupported review status for "+d)
        reviewed.add(d)
        if status=="REVIEW": quarantined.append((d,str(item.get("reason","Insufficient evidence")))); continue
        p=str(item.get("policy","")).upper()
        if p not in {"DIRECT","PROXY","REJECT"}: fail("invalid policy for "+d)
        confidence=item.get("confidence")
        if not isinstance(confidence,(int,float)) or confidence<min_conf: fail("confidence below policy threshold for "+d)
        validate_evidence(d,item.get("evidence"),min_sources)
        if not str(item.get("reason","")).strip() or not str(item.get("reviewed_at","")).strip(): fail("review rationale/date missing for "+d)
        if conditional_overlap(d,conditional):
            quarantined.append((d,"Overlaps an existing conditional AND/OR/NOT rule")); continue
        winner=analyze_candidate(d,False,index)["apex_winner"]
        if winner:
            quarantined.append((d,"Already governed or conflicts with first-match "+winner.policy+" at line "+str(winner.line))); continue
        other=other_rule_match(d,base,p)
        if other:
            quarantined.append((d,other)); continue
        approved.append("DOMAIN,"+d+","+p)
    merged=sorted(set(old_managed+approved))
    block=START+"\n"+("\n".join(merged)+"\n" if merged else "")+END+"\n"
    if base.count(LAYER3)!=1: fail("cannot locate unique insertion point before Layer 3")
    pos=base.index(LAYER3); updated=base[:pos]+block+base[pos:]
    if strip_block(updated)!=base: fail("managed block round-trip failed")
    remaining=[x for x in pending.get("candidates",[]) if x["domain"] not in reviewed]
    pending_out=json.dumps({"schema_version":1,"updated_at":ledger.get("updated_at"),"candidates":remaining},ensure_ascii=False,indent=2)+"\n"
    report=["# GPT-reviewed domain publication","",f"GPT review ledger entries: {len(entries)}",
            f"Pending candidates before publication: {len(queue)}",f"New approved and conflict-free rules: {len(approved)}",
            f"Quarantined or review-only: {len(quarantined)}",f"Remaining pending candidates: {len(remaining)}","",
            "| Domain | Result |","|---|---|"]
    report.extend("| "+d+" | "+reason+" |" for d,reason in quarantined)
    report += ["","Only exact DOMAIN rules are automatically published. Each approval requires independent HTTPS publishers/hosts, rationale, review date and confidence above the configured threshold.",
               "Existing first-match, conditional, DOMAIN-KEYWORD, URL-REGEX and skip-proxy direct-bypass matches are protected.",
               "No suffix-wide rules are generated automatically. Only the managed block and pending queue may change; DNS, nodes, MITM, URL Rewrite and all bytes outside the managed block are protected.",""]
    rendered="\n".join(report)
    if check:
        if updated!=original: fail("config is not synchronized with approved GPT reviews")
        print("PASS: GPT review approvals are synchronized"); return
    CONFIG.write_text(updated,encoding="utf-8"); PENDING.write_text(pending_out,encoding="utf-8")
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(rendered,encoding="utf-8")
    print(rendered)
if __name__=="__main__": main()
