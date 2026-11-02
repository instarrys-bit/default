#!/usr/bin/env python3
"""Conservative DNS lifecycle audit, deletion archive, and restore-by-ID."""
from __future__ import annotations
import concurrent.futures, hashlib, json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"rulesets"
REPORT=ROOT/"reports/lifecycle"
POLICIES=("direct","proxy","reject")
RESOLVERS=(("cloudflare","https://cloudflare-dns.com/dns-query"),("google","https://dns.google/resolve"))
TYPES=("A","AAAA")
PROTECTED=("apple.com","icloud.com","icloud-content.com","google.com","googleapis.com","gstatic.com","youtube.com","microsoft.com","live.com","office.com","windows.net","azure.com","github.com","githubusercontent.com","githubassets.com","cloudflare.com","cloudflare-dns.com","fastly.net","akamai.net","akamaihd.net","amazon.com","amazonaws.com","cloudfront.net","facebook.com","meta.com","instagram.com","whatsapp.com","tencent.com","qq.com","weixin.qq.com","wechat.com","alibaba.com","alibabagroup.com","aliyun.com","taobao.com","tmall.com","jd.com","bytedance.com","douyin.com","volcengine.com","baidu.com","bilibili.com","netease.com","163.com","mi.com","xiaomi.com","weibo.com","meituan.com","pinduoduo.com","cmbchina.com","icbc.com.cn","abchina.com","ccb.com","openai.com","telegram.org","discord.com","steampowered.com","steamcommunity.com","huawei.com","huaweicloud.com","myhuaweicloud.com","hwclouds.com","jd.com","jdcloud.com","360.cn","360.com","360buyimg.com","kuaishou.com","kwai.com","xiaohongshu.com","xhslink.com","iqiyi.com","youku.com","mgtv.com","hunantv.com","sina.com","sina.com.cn","sohu.com","sogou.com","zhihu.com","douban.com","alipay.com","antgroup.com","alibaba-inc.com","aliyuncs.com","tencentcloud.com","qcloud.com","myqcloud.com","miui.com","mijia.com","meituan.net","dianping.com","dpfile.com","temu.com","yangkeduo.com","unionpay.com","unionpay.com.cn","boc.cn","bankofchina.com","bankcomm.com","pingan.com","pingan.com.cn","cib.com.cn","cebbank.com","spdb.com.cn","citicbank.com","psbc.com","chinaunicom.com","10010.com","10086.cn","chinatelecom.com.cn","189.cn","china-mobile.com","ctyun.cn","chinacache.com","wangsu.com","qiniu.com","upyun.com","baishan.com","ucloud.cn","microsoftonline.com","msauth.net","msftauth.net","sharepoint.com","1drv.com","googleusercontent.com","akamaized.net","edgesuite.net","awsstatic.com","azureedge.net")


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


def scope_intersects_rule(left,right):
    def parse(line):
        fields=line.split(",",1)
        if len(fields)!=2 or fields[0] not in {"DOMAIN","DOMAIN-SUFFIX"}:
            return None
        domain=fields[1].lower().strip(".")
        if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+",domain):
            return None
        return fields[0],domain
    a=parse(left); b=parse(right)
    if not a or not b:
        return False
    kind_a,domain_a=a; kind_b,domain_b=b
    if domain_a==domain_b:
        return True
    if kind_a=="DOMAIN-SUFFIX" and (domain_b.endswith("."+domain_a)):
        return True
    if kind_b=="DOMAIN-SUFFIX" and (domain_a.endswith("."+domain_b)):
        return True
    return False


def deletion_confirmed(history):
    if len(history)<2 or any(x.get("status")!="CONFIRMED_NXDOMAIN_OBSERVATION" for x in history):
        return False
    first=datetime.fromisoformat(history[0]["checked_at"].replace("Z","+00:00"))
    last=datetime.fromisoformat(history[-1]["checked_at"].replace("Z","+00:00"))
    return last-first>=timedelta(days=30)


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
    requested={x.strip() for x in os.environ.get("LIFECYCLE_RESTORE_IDS","").split(",") if x.strip()}
    due=bool(state.get("due_milestones") or state.get("monthly_review_due"))
    restore_only=bool(requested) and not due
    if not due and not requested:
        REPORT.mkdir(parents=True,exist_ok=True)
        idle={"status":"not_due","published_rule_count":state.get("published_rule_count",0),"next_milestone":state.get("next_milestone",5000),"max_published_rules":30000}
        (REPORT/"latest.json").write_text(json.dumps(idle,ensure_ascii=False,indent=2)+"\n")
        (REPORT/"latest.md").write_text("# Lifecycle audit\n\nNo lifecycle review is due. Daily incremental review and publishing continue.\n")
        print(json.dumps(idle)); return
    timestamp=datetime.now(timezone.utc).isoformat()
    protected_cfg=json.loads((ROOT/"sources/protected_domains.json").read_text())
    rules={p:set(x.strip() for x in (DIR/(p+".list")).read_text().splitlines() if x.strip() and not x.startswith("#")) for p in POLICIES}
    published_before={p:set(values) for p,values in rules.items()}
    obs_path=DIR/"lifecycle_observations.json"
    archive_path=DIR/"deletion_archive.json"
    queue_path=DIR/"pending_queue.json"
    obs=json.loads(obs_path.read_text()) if obs_path.exists() else {"items":{}}
    archive=json.loads(archive_path.read_text()) if archive_path.exists() else {"items":[]}
    queue=json.loads(queue_path.read_text()) if queue_path.exists() else {"items":[]}
    restored=[]; missing=[]; restore_refused=[]; restored_keys=set()
    for key in requested:
        old=next((x for x in archive["items"] if x["id"]==key and not x.get("restored_at")),None)
        if not old: missing.append(key); continue
        line=str(old.get("rule",""))
        policy=str(old.get("policy","")).lower()
        if policy not in POLICIES or not scope_intersects_rule(line,line):
            restore_refused.append({"id":key,"reason":"archived rule or policy is malformed"})
            continue
        conflict=None
        for other_policy in POLICIES:
            if other_policy!=policy:
                match=next((existing for existing in rules[other_policy] if scope_intersects_rule(line,existing)),None)
                if match:
                    conflict={"policy":other_policy,"rule":match}
                    break
        if conflict is None:
            for queued in queue.get("items",[]):
                queued_policy=str(queued.get("policy","")).lower()
                queued_scope=str(queued.get("scope","exact_candidate"))
                queued_domain=str(queued.get("domain","")).lower()
                queued_line=("DOMAIN-SUFFIX," if queued_scope=="suffix_candidate" else "DOMAIN,")+queued_domain
                if queued_policy in POLICIES and queued_policy!=policy and scope_intersects_rule(line,queued_line):
                    conflict={"policy":queued_policy,"rule":queued_line,"location":"pending_queue"}
                    break
        if conflict:
            restore_refused.append({"id":key,"reason":"restoration would create a cross-policy overlap","conflict":conflict})
            continue
        total=sum(map(len,rules.values()))
        if total<30000:
            rules[policy].add(line); destination="published"
        else:
            queue["items"].append({"policy":policy,"scope":"suffix_candidate" if line.startswith("DOMAIN-SUFFIX,") else "exact_candidate","domain":line.split(",",1)[1],"queued_at":timestamp,"priority":0,"reason":"User-requested restoration"})
            destination="priority_queue"
        old["restored_at"]=timestamp; old["restore_destination"]=destination
        restored_keys.add(key)
        obs.setdefault("items",{}).pop(key,None)
        restored.append({"id":key,"policy":policy,"rule":line,"destination":destination})

    work=[]
    suffix_retained_count=0
    protected_count=0
    for policy in POLICIES:
        for line in sorted(rules[policy]):
            if line.startswith("DOMAIN-SUFFIX,"):
                suffix_retained_count+=1
                continue
            if not line.startswith("DOMAIN,"):
                continue
            domain=line.split(",",1)[1].lower().strip(".")
            identity=rid(policy.upper(),line)
            if protected(domain,protected_cfg):
                protected_count+=1
                continue
            if not restore_only and identity not in restored_keys:
                work.append((identity,policy,line,domain))
    def run(item):
        key,policy,line,domain=item
        return key,policy,line,domain,inspect(domain)
    results={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        for row in pool.map(run,work): results[row[0]]=row[1:]

    deleted=[]; active=0; unknown=0
    archived={x["id"] for x in archive["items"] if not x.get("restored_at")}
    for key,(policy,line,domain,result) in results.items():
        prior=obs.get("items",{}).get(key,{})
        history=list(prior.get("history",[]))
        if result["status"]=="CONFIRMED_NXDOMAIN_OBSERVATION":
            if not history or history[-1].get("checked_at","")[:10]!=timestamp[:10]:
                history.append({"checked_at":timestamp,"status":result["status"],"resolver_status":result["resolver_status"]})
            if deletion_confirmed(history) and key not in archived:
                rules[policy].discard(line)
                entry={"id":key,"policy":policy,"rule":line,"domain":domain,"removed_at":timestamp,"first_confirmed_at":history[0]["checked_at"],"reason":"Two independent DoH resolvers returned NXDOMAIN for A and AAAA on observations at least 30 days apart"}
                archive["items"].append(entry); deleted.append(entry); archived.add(key)
        elif result["status"]=="DNS_EXISTS_OR_NODATA":
            active+=1
            history=[]
        else:
            unknown+=1
            history=[]
        obs.setdefault("items",{})[key]={"policy":policy,"rule":line,"domain":domain,"last_status":result["status"],"history":history,"checked_at":timestamp}

    for policy in POLICIES:
        lines=sorted(rules[policy]); (DIR/(policy+".list")).write_text("\n".join(lines)+("\n" if lines else ""))
    obs["updated_at"]=timestamp; archive["updated_at"]=timestamp; queue["updated_at"]=timestamp
    obs_path.write_text(json.dumps(obs,ensure_ascii=False,indent=2)+"\n")
    archive_path.write_text(json.dumps(archive,ensure_ascii=False,indent=2)+"\n")
    queue_path.write_text(json.dumps(queue,ensure_ascii=False,indent=2)+"\n")
    manifest_path=DIR/"manifest.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["rule_count"]={p:sum(1 for line in rules[p] if line.startswith(("DOMAIN,","DOMAIN-SUFFIX,"))) for p in POLICIES}
        manifest["published_rule_total"]=sum(manifest["rule_count"].values())
        manifest["queued_rule_total"]=len(queue.get("items",[]))
        lifecycle_delta={}
        for policy in POLICIES:
            before_lines=published_before[policy]
            after_lines=rules[policy]
            before_text="\n".join(sorted(before_lines))+("\n" if before_lines else "")
            after_text="\n".join(sorted(after_lines))+("\n" if after_lines else "")
            lifecycle_delta[policy.upper()]={"previous_count":len(before_lines),"current_count":len(after_lines),"added_count":len(after_lines-before_lines),"removed_count":len(before_lines-after_lines),"previous_sha256":hashlib.sha256(before_text.encode()).hexdigest(),"current_sha256":hashlib.sha256(after_text.encode()).hexdigest(),"added_sample":sorted(after_lines-before_lines)[:10],"removed_sample":sorted(before_lines-after_lines)[:10]}
        manifest["rule_lifecycle"]=lifecycle_delta
        manifest["lifecycle_audit_summary"]={"completed_at":timestamp,"deleted_count":len(deleted),"restored_count":len(restored),"unknown_retained_count":unknown,"protected_retained_count":protected_count,"suffix_retained_count":suffix_retained_count}
        manifest["lifecycle_last_audit_at"]=timestamp
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    REPORT.mkdir(parents=True,exist_ok=True)
    options=[{"id":x["id"],"policy":x["policy"],"rule":x["rule"],"removed_at":x["removed_at"]} for x in archive["items"] if not x.get("restored_at")]
    report={"created_at":timestamp,"triggered_milestones":state.get("due_milestones",[]),"monthly_review":state.get("monthly_review_due",False),"deleted":deleted,"active_or_nodata_count":active,"unknown_retained_count":unknown,"protected_count":protected_count,"suffix_retained_count":suffix_retained_count,"restored":restored,"restore_ids_not_found":missing,"restore_refused":restore_refused,"restoration_options":options,"policy":"Only exact DOMAIN hosts confirmed NXDOMAIN by both independent resolvers for A and AAAA, twice at least 30 days apart. Suffix rules are retained because a suffix root can lack DNS records while subdomains remain valid. Protected major-company suffixes are also retained. Resolver errors, missing evidence and source disappearance are retained."}
    (REPORT/"latest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    lines=["# Lifecycle audit",f"Completed: {timestamp}",f"Milestones: {report['triggered_milestones']}",f"Deleted: {len(deleted)}",f"Active/NODATA retained: {active}",f"Unknown retained: {unknown}",f"Protected major-company hosts retained: {protected_count}",f"Suffix rules retained without DNS-root deletion checks: {suffix_retained_count}",f"Restored: {len(restored)}",f"Restoration refused: {len(restore_refused)}","## Deleted entries"]
    lines += [f"- {x['id']} | {x['policy']} | {x['rule']} | first confirmation {x['first_confirmed_at']}" for x in deleted] or ["- None"]
    lines += ["## Restoration refused"]+[f"- {x['id']} | {x['reason']} | {x.get('conflict','')}" for x in restore_refused] or ["- None"]
    lines += ["## Selectable restore IDs"]+[f"- {x['id']} | {x['policy']} | {x['rule']}" for x in options]
    lines += ["","To restore, run the workflow manually and paste selected IDs into restore_ids."]
    (REPORT/"latest.md").write_text("\n".join(lines)+"\n")
    if due:
        from lifecycle_gate import complete_lifecycle_review
        done=complete_lifecycle_review(ROOT,timestamp)
    else:
        done=state
    print(json.dumps({"status":"completed" if due else "restore_only","deleted":len(deleted),"restored":restored,"state":done},ensure_ascii=False))


if __name__=="__main__":
    main()
