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


def acquire_resource_leases(task_id, worker_id, task_lease_token, resource_keys, store, *, lease_seconds=300, now=None):
    if not isinstance(task_id, str) or not task_id or not isinstance(worker_id, str) or not worker_id.strip() or not isinstance(task_lease_token, str) or not task_lease_token:
        raise ValueError("task_id, worker_id and task_lease_token are required")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3600:
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


def assert_resource_lease(queue, *, task_id, worker_id, task_lease_token, resource_key, lease_id, fencing_token, now=None):
    now=now or datetime.now(timezone.utc); key=resource_key(resource_key)
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


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--repository",required=True); p.add_argument("--branch",default="main"); p.add_argument("--queue-path",default="automation/task_queue.json"); p.add_argument("--token-stdin",action="store_true"); p.add_argument("command",choices=["validate"]); a=p.parse_args()
    try:
        token=sys.stdin.read().strip() if a.token_stdin else ""
        if not token: raise ValueError("inspection requires --token-stdin")
        store=GitHubContentsQueueStore(a.repository,a.queue_path,branch=a.branch,token=token); q=store.read().document; validate_envelope(q)
        leases=q.get("resource_leases",{})
        if not isinstance(leases,dict): raise ValueError("resource_leases must be an object")
        for k,v in leases.items(): resource_key(k); checked_record(v,k)
        print(json.dumps({"valid":True,"resource_count":len(leases),"active_count":sum(x["status"]=="ACTIVE" for x in leases.values()),"queue_revision":q["revision"]},sort_keys=True)); return 0
    except (ValueError,OSError) as exc:
        print(f"RESOURCE LEASE INVALID: {exc}",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
