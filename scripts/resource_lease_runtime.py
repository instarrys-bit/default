#!/usr/bin/env python3
"""CAS-backed resource leases with monotonic fencing tokens.

This manages queue metadata only. Writers must invoke assert_resource_lease at
their actual commit boundary before resource exclusion is considered enforced.
"""
from __future__ import annotations
import argparse, json, secrets, sys
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from github_queue_store import GitHubContentsQueueStore


def utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None: raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resource_key(value):
    if not isinstance(value, str) or not value or value != value.strip() or "\\" in value or value.startswith("/") or value.endswith("/"):
        raise ValueError("resource key must be a canonical relative POSIX path")
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(x in {"", ".", ".."} for x in p.parts):
        raise ValueError("resource key contains an unsafe or non-canonical path")
    return value


def normalize_keys(values):
    if not isinstance(values, (list, tuple, set)) or not values:
        raise ValueError("resource_keys must be a non-empty collection")
    keys = [resource_key(x) for x in values]
    if len(keys) != len(set(keys)): raise ValueError("resource_keys contains duplicates")
    return sorted(keys)


def validate_envelope(queue):
    if not isinstance(queue, dict) or queue.get("schema_version") != 1 or isinstance(queue.get("revision"), bool) or not isinstance(queue.get("revision"), int) or queue["revision"] < 0 or not isinstance(queue.get("tasks"), list):
        raise ValueError("resource lease queue envelope is invalid")


def claimed_task(queue, task_id, worker_id, task_token, now):
    task = next((x for x in queue["tasks"] if isinstance(x, dict) and x.get("task_id") == task_id), None)
    if task is None or task.get("status") != "CLAIMED": raise ValueError("resource lease requires a CLAIMED task")
    lease = task.get("lease")
    if not isinstance(lease, dict) or lease.get("owner") != worker_id or not secrets.compare_digest(str(lease.get("token", "")), str(task_token)):
        raise ValueError("task lease owner or token mismatch")
    if utc(lease.get("expires_at")) <= now: raise ValueError("task lease has expired")
    return task


def checked_record(value, key):
    if value is None: return None
    if not isinstance(value, dict) or value.get("status") not in {"ACTIVE", "RELEASED"} or not isinstance(value.get("lease_id"), str) or not value["lease_id"]:
        raise ValueError(f"invalid resource lease record: {key}")
    fence=value.get("fencing_token")
    if isinstance(fence, bool) or not isinstance(fence, int) or fence < 1: raise ValueError(f"invalid fencing token: {key}")
    utc(value.get("expires_at"))
    return value


def acquire_resource_leases_in_queue(queue, task, worker_id, task_lease_token, resource_keys, *, lease_seconds, now, lease_id):
    """Pure queue mutation helper; caller owns the enclosing CAS transaction."""
    validate_envelope(queue)
    claimed_task(queue, task["task_id"], worker_id, task_lease_token, now)
    keys=normalize_keys(resource_keys)
    if isinstance(lease_seconds,bool) or not isinstance(lease_seconds,int) or not 1<=lease_seconds<=21600:
        raise ValueError("lease_seconds must be 1..3600")
    expiry=min(now+timedelta(seconds=lease_seconds),utc(task["lease"]["expires_at"]))
    leases=queue.setdefault("resource_leases",{})
    if not isinstance(leases,dict): raise ValueError("resource_leases must be an object")
    plan={}
    for key in keys:
        old=checked_record(leases.get(key),key)
        if old is None: plan[key]=(lease_id,1,False); continue
        active=old["status"]=="ACTIVE" and utc(old["expires_at"])>now
        same=(old.get("task_id")==task["task_id"] and old.get("worker_id")==worker_id and old.get("task_lease_token")==task_lease_token)
        if active and not same: return {"acquired":False,"blocked_resource":key}
        plan[key]=(old["lease_id"],old["fencing_token"],True) if active else (lease_id,old["fencing_token"]+1,False)
    resources={}
    for key,(current_id,fence,reuse) in plan.items():
        old=leases.get(key) or {}
        leases[key]={"status":"ACTIVE","task_id":task["task_id"],"worker_id":worker_id,
          "task_lease_token":task_lease_token,"lease_id":current_id,"fencing_token":fence,
          "acquired_at":old.get("acquired_at",stamp(now)) if reuse else stamp(now),
          "renewed_at":stamp(now),"expires_at":stamp(expiry),"released_at":None}
        resources[key]={"lease_id":current_id,"fencing_token":fence}
    return {"acquired":True,"resources":resources,"expires_at":stamp(expiry),"lease_seconds":lease_seconds}


def release_resource_leases_in_queue(queue, task, now):
    lease=task.get("resource_lease")
    if not isinstance(lease,dict): return []
    resources=lease.get("resources")
    if not isinstance(resources,dict) or not resources: raise ValueError("task resource lease proof is malformed")
    leases=queue.get("resource_leases")
    if not isinstance(leases,dict): raise ValueError("resource lease registry is missing")
    for key,item in resources.items():
        record=checked_record(leases.get(key),key)
        if record is None or record.get("status")!="ACTIVE" or record.get("task_id")!=task["task_id"] or record.get("lease_id")!=item.get("lease_id") or record.get("fencing_token")!=item.get("fencing_token"):
            raise ValueError(f"stale resource lease cannot be released: {key}")
    for key in resources:
        leases[key]["status"]="RELEASED"; leases[key]["released_at"]=stamp(now); leases[key]["expires_at"]=stamp(now)
    lease["status"]="RELEASED"; lease["released_at"]=stamp(now)
    return sorted(resources)


def renew_resource_leases_in_queue(queue, task, now):
    lease=task.get("resource_lease")
    if not isinstance(lease,dict): return True
    resources=lease.get("resources")
    seconds=lease.get("lease_seconds")
    if not isinstance(resources,dict) or not resources or isinstance(seconds,bool) or not isinstance(seconds,int) or not 1<=seconds<=21600:
        raise ValueError("task resource lease renewal contract is malformed")
    leases=queue.get("resource_leases")
    if not isinstance(leases,dict): raise ValueError("resource lease registry is missing")
    for key,item in resources.items():
        record=checked_record(leases.get(key),key)
        if record is None or record.get("status")!="ACTIVE" or record.get("task_id")!=task["task_id"] or record.get("lease_id")!=item.get("lease_id") or record.get("fencing_token")!=item.get("fencing_token"):
            return False
        if utc(record["expires_at"])<=now: return False
    expiry=stamp(now+timedelta(seconds=seconds))
    for key in resources:
        leases[key]["expires_at"]=expiry; leases[key]["renewed_at"]=stamp(now)
    lease["expires_at"]=expiry
    return True


def extend_resource_leases_for_verification(queue, task, now):
    lease=task.get("resource_lease")
    if not isinstance(lease,dict): return
    seconds=lease.get("lease_seconds")
    resources=lease.get("resources")
    if isinstance(seconds,bool) or not isinstance(seconds,int) or not 1<=seconds<=21600 or not isinstance(resources,dict):
        raise ValueError("task resource lease metadata is malformed")
    leases=queue.get("resource_leases")
    if not isinstance(leases,dict): raise ValueError("resource lease registry is missing")
    expiry=stamp(now+timedelta(seconds=seconds))
    for key,item in resources.items():
        record=checked_record(leases.get(key),key)
        if record is None or record.get("status")!="ACTIVE" or record.get("task_id")!=task["task_id"] or record.get("lease_id")!=item.get("lease_id") or record.get("fencing_token")!=item.get("fencing_token"):
            raise ValueError(f"resource lease changed before verification: {key}")
    for key in resources:
        leases[key]["expires_at"]=expiry; leases[key]["renewed_at"]=stamp(now)
    lease["expires_at"]=expiry


def acquire_resource_leases(task_id, worker_id, task_lease_token, resource_keys, store, *, lease_seconds=300, now=None):
    if not isinstance(task_id, str) or not task_id or not isinstance(worker_id, str) or not worker_id.strip() or not isinstance(task_lease_token, str) or not task_lease_token:
        raise ValueError("task_id, worker_id and task_lease_token are required")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 21600:
        raise ValueError("lease_seconds must be 1..3600")
    keys=normalize_keys(resource_keys); now=now or datetime.now(timezone.utc); new_id=secrets.token_hex(16)
    def mutate(queue):
        validate_envelope(queue)
        task=claimed_task(queue, task_id, worker_id, task_lease_token, now)
        expiry=min(now+timedelta(seconds=lease_seconds), utc(task["lease"]["expires_at"]))
        leases=queue.setdefault("resource_leases", {})
        if not isinstance(leases, dict): raise ValueError("resource_leases must be an object")
        plan={}
        for key in keys:
            old=checked_record(leases.get(key), key)
            if old is None:
                plan[key]=(new_id, 1, False); continue
            active=old["status"]=="ACTIVE" and utc(old["expires_at"])>now
            same=(old.get("task_id")==task_id and old.get("worker_id")==worker_id and old.get("task_lease_token")==task_lease_token)
            if active and not same:
                return queue, {"acquired":False,"blocked_resource":key,"reason":"resource held by another active task"}
            plan[key]=(old["lease_id"],old["fencing_token"],True) if active else (new_id,old["fencing_token"]+1,False)
        for key,(lease_id,fence,reuse) in plan.items():
            old=leases.get(key) or {}
            leases[key]={"status":"ACTIVE","task_id":task_id,"worker_id":worker_id,"task_lease_token":task_lease_token,"lease_id":lease_id,"fencing_token":fence,"acquired_at":old.get("acquired_at",stamp(now)) if reuse else stamp(now),"renewed_at":stamp(now),"expires_at":stamp(expiry),"released_at":None}
        queue["revision"]+=1
        return queue,{"acquired":True,"task_id":task_id,"worker_id":worker_id,"resources":{k:{"lease_id":plan[k][0],"fencing_token":plan[k][1]} for k in keys},"expires_at":stamp(expiry)}
    return store.mutate(mutate)


def assert_resource_lease(queue, *, task_id, worker_id, task_lease_token, resource_path, lease_id, fencing_token, now=None):
    now=now or datetime.now(timezone.utc); key=resource_key(resource_path)
    validate_envelope(queue); claimed_task(queue,task_id,worker_id,task_lease_token,now)
    leases=queue.get("resource_leases")
    if not isinstance(leases,dict): raise ValueError("resource lease registry is missing")
    record=checked_record(leases.get(key),key)
    if record is None or record["status"]!="ACTIVE" or record.get("task_id")!=task_id or record.get("worker_id")!=worker_id or record.get("task_lease_token")!=task_lease_token or record.get("lease_id")!=lease_id or record.get("fencing_token")!=fencing_token:
        raise ValueError(f"resource lease fencing check failed: {key}")
    if utc(record["expires_at"])<=now: raise ValueError(f"resource lease expired: {key}")
    return True


def release_resource_leases(task_id, worker_id, task_lease_token, resources, store, *, now=None):
    if not isinstance(resources,dict) or not resources: raise ValueError("resources must be a non-empty lease map")
    normalized={}
    for raw,item in resources.items():
        key=resource_key(raw)
        if not isinstance(item,dict) or not isinstance(item.get("lease_id"),str) or not item["lease_id"] or isinstance(item.get("fencing_token"),bool) or not isinstance(item.get("fencing_token"),int) or item["fencing_token"]<1:
            raise ValueError(f"invalid resource token: {key}")
        normalized[key]=item
    now=now or datetime.now(timezone.utc)
    def mutate(queue):
        validate_envelope(queue); leases=queue.get("resource_leases")
        if not isinstance(leases,dict): raise ValueError("resource lease registry is missing")
        for key,item in normalized.items():
            record=checked_record(leases.get(key),key)
            if record is None or record["status"]!="ACTIVE" or record.get("task_id")!=task_id or record.get("worker_id")!=worker_id or record.get("task_lease_token")!=task_lease_token or record.get("lease_id")!=item["lease_id"] or record.get("fencing_token")!=item["fencing_token"]:
                raise ValueError(f"stale or mismatched resource release: {key}")
        for key in normalized:
            leases[key]["status"]="RELEASED"; leases[key]["released_at"]=stamp(now); leases[key]["expires_at"]=stamp(now)
        queue["revision"]+=1
        return queue,{"released":sorted(normalized),"fencing_counters_preserved":True}
    return store.mutate(mutate)


def assert_workflow_resource_lease(queue, task_id, proof, *, now=None):
    """Validate the live durable queue lease at a workflow publication boundary."""
    now=now or datetime.now(timezone.utc)
    validate_envelope(queue)
    if not isinstance(task_id,str) or not task_id or not isinstance(proof,dict) or not proof:
        raise ValueError("workflow task ID and resource proof are required")
    task=next((x for x in queue["tasks"] if isinstance(x,dict) and x.get("task_id")==task_id),None)
    if task is None or task.get("status") not in {"CLAIMED","VERIFYING"}:
        raise ValueError("workflow task is not active in CLAIMED or VERIFYING state")
    if task.get("target_program_id")!="workflow_auto_sync" or task.get("requester_program_id")!="workflow_automation_watchdog":
        raise ValueError("resource proof is not bound to the Watchdog production workflow")
    intent=task.get("dispatch_intent")
    attempt=task.get("attempts")
    if (not isinstance(intent,dict) or intent.get("task_id")!=task_id
            or intent.get("workflow_path")!=".github/workflows/auto_sync.yml"
            or intent.get("ref")!="main" or intent.get("dispatch_attempt")!=attempt
            or intent.get("correlation_id")!=f"{task_id}-a{attempt}"):
        raise ValueError("durable dispatch intent does not authorize this workflow")
    task_lease=task.get("resource_lease")
    if not isinstance(task_lease,dict) or task_lease.get("status")!="ACTIVE":
        raise ValueError("task has no active resource lease proof")
    declared=task_lease.get("resources")
    if not isinstance(declared,dict) or set(declared)!=set(proof):
        raise ValueError("workflow resource proof does not match the task's declared resource set")
    leases=queue.get("resource_leases")
    if not isinstance(leases,dict):
        raise ValueError("durable resource lease registry is missing")
    for raw_key,item in proof.items():
        key=resource_key(raw_key)
        if not isinstance(item,dict):
            raise ValueError(f"resource proof is malformed: {key}")
        record=checked_record(leases.get(key),key)
        if (record is None or record.get("status")!="ACTIVE"
                or record.get("task_id")!=task_id
                or record.get("lease_id")!=item.get("lease_id")
                or record.get("fencing_token")!=item.get("fencing_token")
                or declared[key]!=item):
            raise ValueError(f"resource lease is stale or fenced: {key}")
        if utc(record["expires_at"])<=now:
            raise ValueError(f"resource lease has expired: {key}")
    return {"valid":True,"task_id":task_id,"resource_count":len(proof),
            "fencing_tokens":{key:value["fencing_token"] for key,value in proof.items()},
            "queue_revision":queue["revision"]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository",required=True)
    p.add_argument("--branch",default="main")
    p.add_argument("--queue-path",default="automation/task_queue.json")
    p.add_argument("--token-stdin",action="store_true")
    p.add_argument("--task-id")
    p.add_argument("--proof-json")
    p.add_argument("command",choices=["validate","assert-workflow"])
    a=p.parse_args()
    try:
        token=sys.stdin.read().strip() if a.token_stdin else ""
        if not token: raise ValueError("inspection requires --token-stdin")
        store=GitHubContentsQueueStore(a.repository,a.queue_path,branch=a.branch,token=token)
        q=store.read().document; validate_envelope(q)
        if a.command=="assert-workflow":
            if not a.task_id or not a.proof_json: raise ValueError("assert-workflow requires --task-id and --proof-json")
            try: proof=json.loads(a.proof_json)
            except json.JSONDecodeError as exc: raise ValueError("resource proof must be valid JSON") from exc
            result=assert_workflow_resource_lease(q,a.task_id,proof)
            print(json.dumps(result,sort_keys=True)); return 0
        leases=q.get("resource_leases",{})
        if not isinstance(leases,dict): raise ValueError("resource_leases must be an object")
        for k,v in leases.items(): resource_key(k); checked_record(v,k)
        print(json.dumps({"valid":True,"resource_count":len(leases),"active_count":sum(x["status"]=="ACTIVE" for x in leases.values()),"queue_revision":q["revision"]},sort_keys=True)); return 0
    except (ValueError,OSError) as exc:
        print(f"RESOURCE LEASE INVALID: {exc}",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
