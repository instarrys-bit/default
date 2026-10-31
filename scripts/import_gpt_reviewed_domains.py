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
def fail(m): raise SystemExit("ERROR: "+m)
def blob(data): return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()
def strip_block(text):
    lines=text.splitlines(keepends=True)
    a=[i for i,x in enumerate(lines) if x.strip()==START]; b=[i for i,x in enumerate(lines) if x.strip()==END]
    if not a and not b: return text
    if len(a)!=1 or len(b)!=1 or a[0]>=b[0]: fail("managed block markers malformed")
    return "".join(lines[:a[0]]+lines[b[0]+1:])
def conditional_overlap(domain,conditional):
    for _,raw in conditional:
        for _,d in COND_RE.findall(raw):
            d=d.lower().strip(".")
            if domain==d or domain.endswith("."+d) or d.endswith("."+domain): return True
    return False
def load_rules_from_text(content):
    import tempfile
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".conf",delete=False) as f:
        f.write(content); name=f.name
    try: return load_domain_rules(Path(name))
    finally: Path(name).unlink(missing_ok=True)
def main():
    check="--check" in sys.argv
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    original=CONFIG.read_text(encoding="utf-8"); base=strip_block(original)
    if blob(base.encode("utf-8"))!=policy["canonical_config"]["approved_git_blob_sha"]:
        fail("config outside managed block differs from approved baseline")
    if not REVIEWS.exists() or not PENDING.exists(): fail("review ledger or pending queue missing")
    ledger=json.loads(REVIEWS.read_text(encoding="utf-8")); pending=json.loads(PENDING.read_text(encoding="utf-8"))
    queue={x["domain"]:x for x in pending.get("candidates",[])}
    entries=ledger.get("reviews",[])
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
        if status=="REVIEW":
            quarantined.append((d,str(item.get("reason","Insufficient evidence")))); continue
        p=str(item.get("policy","")).upper()
        if p not in {"DIRECT","PROXY","REJECT"}: fail("invalid policy for "+d)
        confidence=item.get("confidence")
        if not isinstance(confidence,(int,float)) or confidence<0.90: fail("confidence below 0.90 for "+d)
        evidence=item.get("evidence")
        if not isinstance(evidence,list) or len(evidence)<2: fail("fewer than two evidence sources for "+d)
        hosts=set()
        for ev in evidence:
            u=str(ev.get("url","")).strip()
            if not u.startswith("https://"): fail("non-HTTPS evidence URL for "+d)
            host=urlparse(u).hostname
            if not host: fail("invalid evidence host for "+d)
            hosts.add(host.lower())
        if len(hosts)<2: fail("evidence sources are not independent for "+d)
        if not str(item.get("reason","")).strip() or not str(item.get("reviewed_at","")).strip():
            fail("review rationale/date missing for "+d)
        if conditional_overlap(d,conditional):
            quarantined.append((d,"Overlaps an existing conditional AND/OR/NOT rule")); continue
        winner=analyze_candidate(d,False,index)["apex_winner"]
        if winner:
            if winner.policy==p: quarantined.append((d,"Already governed by "+p+"; no duplicate imported"))
            else: quarantined.append((d,"Conflicts with first-match "+winner.policy+" at line "+str(winner.line)))
            continue
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
    report += ["","Only exact DOMAIN rules are automatically published. Each approval requires two independent HTTPS evidence hosts, rationale, review date and confidence >= 0.90.",
               "No suffix-wide rules are generated automatically. Existing rules win; conflicts and conditional-rule overlaps are quarantined.",
               "Only the managed block and pending queue may change. DNS, nodes, MITM, URL Rewrite and all bytes outside the managed block are protected.",""]
    rendered="\n".join(report)
    if check:
        if updated!=original: fail("config is not synchronized with approved GPT reviews")
        print("PASS: GPT review approvals are synchronized"); return
    CONFIG.write_text(updated,encoding="utf-8"); PENDING.write_text(pending_out,encoding="utf-8")
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(rendered,encoding="utf-8")
    print(rendered)
if __name__=="__main__": main()
