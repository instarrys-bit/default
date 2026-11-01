#!/usr/bin/env python3
"""Conservative DNS lifecycle audit, deletion archive, and restore-by-ID."""
from __future__ import annotations
import concurrent.futures, hashlib, json, os, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"rulesets"
REPORT=ROOT/"reports/lifecycle"
POLICIES=("direct","proxy","reject")
RESOLVERS=(("cloudflare","https://cloudflare-dns.com/dns-query"),("google","https://dns.google/resolve"))
TYPES=("A","AAAA")
PROTECTED=("apple.com","icloud.com","google.com","googleapis.com","gstatic.com","youtube.com","microsoft.com","live.com","office.com","windows.net","azure.com","amazon.com","amazonaws.com","cloudfront.net","tencent.com","qq.com","weixin.qq.com","wechat.com","alibaba.com","alibabagroup.com","aliyun.com","taobao.com","tmall.com","jd.com","bytedance.com","douyin.com","volcengine.com","baidu.com","bilibili.com","netease.com","163.com","mi.com","xiaomi.com","weibo.com","meituan.com","pinduoduo.com","cmbchina.com","icbc.com.cn","abchina.com","ccb.com")


def rid(policy,line):
    return hashlib.sha256((policy+"|"+line).encode()).hexdigest()[:20]


def protected(domain, config):
    domain=domain.lower().strip(".")
    suffixes=set(PROTECTED)|{str(x).lower().strip(".") for x in config.get("protected_suffixes",[])}
    exact={str(x).lower().strip(".") for x in config.get("protected_exact",[])}
    return domain in exact or any(domain==s or domain.endswith("."+s) for s in suffixes)


def query(endpoint,domain,kind):
    url=endpoint+("?" if "?" not in endpoint else "&")+urllib.parse.urlencode({"name":domain,"type":kind})
    req=urllib.request.Request(url,headers={"accept":"application/dns-json","user-agent":"domain-lifecycle-audit/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=8) as res:
            data=json.loads(res.read().decode())
        return int(data.get("Status"))
    except Exception:
        return None


def inspect(domain):
    result={}
    for resolver,endpoint in RESOLVERS:
        for kind in TYPES:
            result[resolver+"_"+kind]=query(endpoint,domain,kind)
    values=list(result.values())
    if len(values)==4 and all(x==3 for x in values):
        status="CONFIRMED_NXDOMAIN_OBSERVATION"
    elif any(x==0 for x in values):
        status="DNS_EXISTS_OR_NODATA"
    else:
        status="UNKNOWN_OR_RESOLVER_ERROR"
    return {"status":status,"resolver_status":result}


def main():
    state_path=DIR/"lifecycle_state.json"
    state=json.loads(state_path.read_text())
    if not state.get("due_milestones") and not state.get("monthly_review_due"):
        print(json.dumps({"status":"not_due"})); return
    timestamp=datetime.now(timezone.utc).isoformat()
    protected_cfg=json.loads((ROOT/"sources/protected_domains.json").read_text())
    rules={p:set(x.strip() for x in (DIR/(p+".list")).read_text().splitlines() if x.strip() and not x.startswith("#")) for p in POLICIES}
    obs_path=DIR/"lifecycle_observations.json"
    archive_path=DIR/"deletion_archive.json"
    queue_path=DIR/"pending_queue.json"
    obs=json.loads(obs_path.read_text()) if obs_path.exists() else {"items":{}}
    archive=json.loads(archive_path.read_text()) if archive_path.exists() else {"items":[]}
    queue=json.loads(queue_path.read_text()) if queue_path.exists() else {"items":[]}
    restored=[]; missing=[]
    for key in [x.strip() for x in os.environ.get("LIFECYCLE_RESTORE_IDS","").split(",") if x.strip()]:
        old=next((x for x in archive["items"] if x["id"]==key and not x.get("restored_at")),None)
        if not old: missing.append(key); continue
        total=sum(map(len,rules.values()))
        line=old["rule"]; policy=old["policy"]
        if total<30000:
            rules[policy].add(line); destination="published"
        else:
            queue["items"].append({"policy":policy,"scope":"suffix_candidate" if line.startswith("DOMAIN-SUFFIX,") else "exact_candidate","domain":line.split(",",1)[1],"queued_at":timestamp,"priority":0,"reason":"User-requested restoration"})
            destination="priority_queue"
        old["restored_at"]=timestamp; old["restore_destination"]=destination
        restored.append({"id":key,"policy":policy,"rule":line,"destination":destination})

    work=[]
    for policy in POLICIES:
        for line in sorted(rules[policy]):
            if not line.startswith(("DOMAIN,","DOMAIN-SUFFIX,")): continue
            domain=line.split(",",1)[1].lower().strip(".")
            if not protected(domain,protected_cfg): work.append((rid(policy.upper(),line),policy,line,domain))
    def run(item):
        key,policy,line,domain=item
        return key,policy,line,domain,inspect(domain)
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        for row in pool.map(run,work): results[row[0]]=row[1:]

    deleted=[]; active=0; unknown=0
    archived={x["id"] for x in archive["items"]}
    for key,(policy,line,domain,result) in results.items():
        prior=obs.get("items",{}).get(key,{})
        history=list(prior.get("history",[]))
        if result["status"]=="CONFIRMED_NXDOMAIN_OBSERVATION":
            if not history or history[-1].get("status")!=result["status"]:
                history.append({"checked_at":timestamp,"status":result["status"],"resolver_status":result["resolver_status"]})
            eligible=False
            if len(history)>=2:
                first=datetime.fromisoformat(history[-2]["checked_at"].replace("Z","+00:00"))
                second=datetime.fromisoformat(history[-1]["checked_at"].replace("Z","+00:00"))
                eligible=second-first>=timedelta(days=30)
            if eligible and key not in archived:
                rules[policy].discard(line)
                entry={"id":key,"policy":policy,"rule":line,"domain":domain,"removed_at":timestamp,"first_confirmed_at":history[-2]["checked_at"],"reason":"Two independent DoH resolvers returned NXDOMAIN for A and AAAA on observations at least 30 days apart"}
                archive["items"].append(entry); deleted.append(entry); archived.add(key)
        elif result["status"]=="DNS_EXISTS_OR_NODATA": active+=1
        else: unknown+=1
        obs.setdefault("items",{})[key]={"policy":policy,"rule":line,"domain":domain,"last_status":result["status"],"history":history,"checked_at":timestamp}

    for policy in POLICIES:
        lines=sorted(rules[policy]); (DIR/(policy+".list")).write_text("\n".join(lines)+("\n" if lines else ""))
    obs["updated_at"]=timestamp; archive["updated_at"]=timestamp; queue["updated_at"]=timestamp
    obs_path.write_text(json.dumps(obs,ensure_ascii=False,indent=2)+"\n")
    archive_path.write_text(json.dumps(archive,ensure_ascii=False,indent=2)+"\n")
    queue_path.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+"\n")
    REPORT.mkdir(parents=True,exist_ok=True)
    options=[{"id":x["id"],"policy":x["policy"],"rule":x["rule"],"removed_at":x["removed_at"]} for x in archive["items"] if not x.get("restored_at")]
    report={"created_at":timestamp,"triggered_milestones":state.get("due_milestones",[]),"monthly_review":state.get("monthly_review_due",False),"deleted":deleted,"active_or_nodata_count":active,"unknown_retained_count":unknown,"restored":restored,"restore_ids_not_found":missing,"restoration_options":options,"policy":"Only confirmed NXDOMAIN on both independent resolvers for A and AAAA, twice at least 30 days apart. Protected major-company suffixes are never auto-deleted. Resolver errors, missing evidence and source disappearance are retained."}
    (REPORT/"latest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    lines=["# Lifecycle audit",f"Completed: {timestamp}",f"Milestones: {report['triggered_milestones']}",f"Deleted: {len(deleted)}",f"Active/NODATA retained: {active}",f"Unknown retained: {unknown}",f"Restored: {len(restored)}","## Deleted entries"]
    lines += [f"- {x['id']} | {x['policy']} | {x['rule']} | first confirmation {x['first_confirmed_at']}" for x in deleted] or ["- None"]
    lines += ["## Selectable restore IDs"]+[f"- {x['id']} | {x['policy']} | {x['rule']}" for x in options]
    lines += ["","To restore, run the workflow manually and paste selected IDs into restore_ids."]
    (REPORT/"latest.md").write_text("\n".join(lines)+"\n")
    from lifecycle_gate import complete_lifecycle_review
    done=complete_lifecycle_review(ROOT,timestamp)
    print(json.dumps({"status":"completed","deleted":len(deleted),"restored":restored,"state":done},ensure_ascii=False))


if __name__=="__main__":
    main()
