#!/usr/bin/env python3
"""Independently verify the committed remote rule sets, manifest, queue and protected config."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()

import argparse
import hashlib
import json
import re
import subprocess

POLICIES=("DIRECT","PROXY","REJECT")
DOMAIN_RE=re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+bytes([0])+data).hexdigest()

def verify_artifacts(manifest, queue, rule_files, policy, config_bytes):
    expected={p.lower()+".list" for p in POLICIES}
    if set(rule_files)!=expected:
        raise ValueError("remote rule-set file inventory is not exactly DIRECT/PROXY/REJECT")
    if set(manifest.get("outputs",[]))!=expected or len(manifest.get("outputs",[]))!=len(expected):
        raise ValueError("manifest output inventory does not match the three policy files")
    if int(manifest.get("max_published_rules",0))!=30000 or int(queue.get("max_published_rules",0))!=30000:
        raise ValueError("published capacity must remain exactly 30,000")
    counts={}
    seen={}
    sha_report={}
    for policy_name in POLICIES:
        name=policy_name.lower()+".list"
        payload=rule_files[name]
        digest=hashlib.sha256(payload).hexdigest()
        lifecycle=manifest.get("rule_lifecycle",{}).get(policy_name,{})
        if lifecycle.get("current_sha256")!=digest:
            raise ValueError("remote SHA-256 does not match manifest for "+name)
        lines=[line.strip() for line in payload.decode("utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if len(lines)!=len(set(lines)):
            raise ValueError("duplicate rules found in "+name)
        for line in lines:
            fields=line.split(",",1)
            if len(fields)!=2 or fields[0] not in {"DOMAIN","DOMAIN-SUFFIX"} or not DOMAIN_RE.fullmatch(fields[1].lower().rstrip(".")):
                raise ValueError("invalid rule syntax in "+name+": "+line)
            domain=fields[1].lower().rstrip(".")
            if domain in seen and seen[domain]!=policy_name:
                raise ValueError("cross-policy published conflict: "+domain)
            seen[domain]=policy_name
        counts[policy_name]=len(lines)
        sha_report[name]=digest
    total=sum(counts.values())
    if counts!=manifest.get("rule_count") or total!=int(manifest.get("published_rule_total",-1)):
        raise ValueError("published rule counts do not match manifest")
    if total>30000:
        raise ValueError("published rule count exceeds the 30,000 hard cap")
    queue_items=queue.get("items",[])
    if not isinstance(queue_items,list) or int(queue.get("queued_count",-1))!=len(queue_items):
        raise ValueError("pending queue count does not match queue contents")
    if int(manifest.get("queued_rule_total",-1))!=len(queue_items):
        raise ValueError("pending queue count does not match manifest")
    queued_seen=set()
    for item in queue_items:
        policy_name=str(item.get("policy","")).upper()
        scope=str(item.get("scope","exact_candidate"))
        domain=str(item.get("domain","")).lower().rstrip(".")
        if policy_name not in POLICIES or scope not in {"exact_candidate","suffix_candidate"} or not DOMAIN_RE.fullmatch(domain):
            raise ValueError("invalid pending queue item")
        if domain in seen:
            raise ValueError("queued domain is already published: "+domain)
        if domain in queued_seen:
            raise ValueError("duplicate or cross-policy queue domain: "+domain)
        queued_seen.add(domain)
    guard=policy.get("managed_config_guard",{})
    approved_sha=guard.get("approved_git_blob_sha")
    actual_sha=git_blob_sha(config_bytes)
    if not approved_sha or approved_sha!=actual_sha:
        raise ValueError("protected ss.conf Git blob SHA differs from the approved baseline")
    if manifest.get("review_engine")!="deterministic-domain-audit/4.1":
        raise ValueError("manifest reviewer version does not match the deployed deterministic reviewer")
    return {"status":"PASS","published_rule_total":total,"rule_count":counts,"rule_sha256":sha_report,"queued_rule_total":len(queue_items),"capacity_remaining":30000-total,"ss_conf_git_blob_sha":actual_sha}

def git_show(ref: str, path: str) -> bytes:
    result=subprocess.run(["git","show",ref+":"+path],check=True,capture_output=True)
    return result.stdout

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ref",default="origin/main")
    args=parser.parse_args()
    ref=args.ref
    commit=subprocess.run(["git","rev-parse",ref],check=True,capture_output=True,text=True).stdout.strip()
    manifest=json.loads(git_show(ref,"rulesets/manifest.json"))
    queue=json.loads(git_show(ref,"rulesets/pending_queue.json"))
    policy=json.loads(git_show(ref,"sources/policy.json"))
    config=git_show(ref,"modules/uu.conf")
    files={p.lower()+".list":git_show(ref,"rulesets/"+p.lower()+".list") for p in POLICIES}
    result=verify_artifacts(manifest,queue,files,policy,config)
    result["remote_ref"]=ref
    result["remote_commit"]=commit
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
