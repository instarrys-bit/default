#!/usr/bin/env python3
"""Local single-writer task queue runtime; no network or workflow dispatch."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()

import argparse, fcntl, json, os, secrets, sys, tempfile, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QUEUE=ROOT/"automation"/"task_queue.json"
REGISTRY=ROOT/"automation"/"program_registry.json"

def now_utc():
    return datetime.now(timezone.utc)

def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def read_json(path):
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value,dict): raise ValueError(f"{path} must contain a JSON object")
    return value

@contextmanager
def queue_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

def atomic_write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=f".{path.name}.",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(payload,stream,ensure_ascii=False,indent=2,sort_keys=True)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except Exception:
        try: os.unlink(name)
        except FileNotFoundError: pass
        raise

def context(queue_path,registry_path):
    queue=read_json(queue_path); registry=read_json(registry_path)
    programs=registry.get("programs")
    if not isinstance(programs,list): raise ValueError("program registry programs must be an array")
    by_id={p.get("id"):p for p in programs if isinstance(p,dict) and isinstance(p.get("id"),str)}
    if queue.get("schema_version")!=1 or not isinstance(queue.get("revision"),int) or isinstance(queue.get("revision"),bool) or queue["revision"]<0 or not isinstance(queue.get("tasks"),list):
        raise ValueError("task queue envelope is invalid")
    return queue,by_id

def authorize(task,by_id):
    requester,target=task.get("requester_program_id"),task.get("target_program_id")
    if requester not in by_id or target not in by_id: raise ValueError("requester and target must be registered")
    program=by_id[target]; policy=program.get("orchestration",{})
    if policy.get("enabled") is not True: raise ValueError(f"target program is not enabled for orchestration: {target}")
    if requester not in policy.get("allowed_callers",[]): raise ValueError(f"requester is not allowed to call target: {requester}")
    if task.get("capability") not in program.get("capabilities",[]): raise ValueError("target does not declare requested capability")
    maximum=policy.get("max_attempts"); timeout=policy.get("timeout_seconds")
    if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=5: raise ValueError("enabled target must set max_attempts from 1 to 5")
    if isinstance(timeout,bool) or not isinstance(timeout,int) or not 1<=timeout<=3600: raise ValueError("target timeout must be from 1 to 3600 seconds")
    return policy


def manual_authorization_context_from_environment():
    """Trusted GitHub Actions identity for the current run attempt."""
    return {key: os.environ.get(env, "") for key, env in {
        "repository": "GITHUB_REPOSITORY", "workflow_ref": "GITHUB_WORKFLOW_REF",
        "event": "GITHUB_EVENT_NAME", "actor": "GITHUB_ACTOR",
        "actor_id": "GITHUB_ACTOR_ID", "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT", "ref": "GITHUB_REF", "sha": "GITHUB_SHA", "manual_audit_requested": "GITHUB_MANUAL_AUDIT_REQUEST",
    }.items()}


def validate_manual_authorization(task, context=None):
    """Reject forged, stale, replayed, or non-Watchdog manual audit requests."""
    payload = task.get("input") if isinstance(task, dict) else None
    if not isinstance(payload, dict):
        return
    authorization_fields = {"authorization_run_id", "authorization_run_attempt",
                            "authorization_actor", "authorization_actor_id",
                            "authorization_repository", "authorization_workflow_ref",
                            "authorization_event", "authorization_ref", "authorization_head_sha"}
    if payload.get("production_decision") != "USER_AUTHORIZED_MANUAL_AUDIT":
        if authorization_fields.intersection(payload):
            raise ValueError("manual authorization marker is invalid or incomplete")
        return
    context = context if isinstance(context, dict) else manual_authorization_context_from_environment()
    required = ("repository", "workflow_ref", "event", "actor", "actor_id",
                "run_id", "run_attempt", "ref", "sha", "manual_audit_requested")
    if any(not isinstance(context.get(k), str) or not context[k].strip() for k in required):
        raise ValueError("trusted GitHub Actions run identity is incomplete")
    expected_workflow = f'{context["repository"]}/.github/workflows/automation-watchdog.yml@refs/heads/main'
    if (context["event"] != "workflow_dispatch" or context["ref"] != "refs/heads/main"
            or context["workflow_ref"] != expected_workflow
            or not context["actor_id"].isdigit() or not context["run_id"].isdigit()
            or not context["run_attempt"].isdigit() or context["manual_audit_requested"] != "true"):
        raise ValueError("manual audit must originate from a main-branch Watchdog workflow_dispatch")
    expected = {
        "authorization_run_id": context["run_id"],
        "authorization_run_attempt": context["run_attempt"],
        "authorization_actor": context["actor"],
        "authorization_actor_id": context["actor_id"],
        "authorization_repository": context["repository"],
        "authorization_workflow_ref": context["workflow_ref"],
        "authorization_event": context["event"],
        "authorization_ref": context["ref"],
        "authorization_head_sha": context["sha"],
        "authorization_requested": True,
        "baseline_source_event": context["event"],
        "baseline_source_sha": context["sha"],
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"manual audit authorization does not match trusted workflow run: {key}")
    if not isinstance(payload.get("production_fingerprint"), str) or not payload["production_fingerprint"]:
        raise ValueError("manual audit authorization requires a production input fingerprint")

def enqueue_task(task,queue_path=QUEUE,registry_path=REGISTRY,now=None):
    if not isinstance(task,dict): raise ValueError("task payload must be an object")
    with queue_lock(queue_path):
        queue,by_id=context(queue_path,registry_path); policy=authorize(task,by_id)
        idem=task.get("idempotency_key")
        if not isinstance(idem,str) or not 1<=len(idem)<=200: raise ValueError("idempotency_key must contain 1 to 200 characters")
        for old in queue["tasks"]:
            if old.get("idempotency_key")==idem:
                fields=("requester_program_id","target_program_id","capability","priority","input")
                if any(old.get(k)!=task.get(k,50 if k=="priority" else {}) for k in fields):
                    raise ValueError("idempotency_key is already used for a different task payload")
                return {"created":False,"task":old}
        priority=task.get("priority",50); payload=task.get("input",{})
        if isinstance(priority,bool) or not isinstance(priority,int) or not 0<=priority<=100: raise ValueError("priority must be an integer from 0 to 100")
        if not isinstance(payload,dict): raise ValueError("input must be an object")
        now=now or now_utc()
        item={"task_id":"task_"+uuid.uuid4().hex[:24],"idempotency_key":idem,"trace_id":str(task.get("trace_id") or uuid.uuid4().hex),
              "requester_program_id":task["requester_program_id"],"target_program_id":task["target_program_id"],"capability":task["capability"],
              "created_at":stamp(now),"not_before":stamp(now),"priority":priority,"status":"QUEUED","attempts":0,
              "max_attempts":policy["max_attempts"],"input":payload,"lease":None,"result":None,"last_error":None,"state_history":["QUEUED"]}
        queue["tasks"].append(item); queue["revision"]+=1; atomic_write(queue_path,queue)
        return {"created":True,"task":item}

def claim_next(worker_id,queue_path=QUEUE,registry_path=REGISTRY,now=None):
    if not isinstance(worker_id,str) or not worker_id.strip(): raise ValueError("worker_id is required")
    now=now or now_utc()
    with queue_lock(queue_path):
        queue,by_id=context(queue_path,registry_path); eligible=[]
        for task in queue["tasks"]:
            if task.get("status")!="QUEUED": continue
            if datetime.fromisoformat(task["not_before"].replace("Z","+00:00"))>now: continue
            policy=authorize(task,by_id); eligible.append((task,policy))
        if not eligible: return None
        eligible.sort(key=lambda pair:(-pair[0]["priority"],pair[0]["created_at"],pair[0]["task_id"]))
        task,policy=eligible[0]
        task["status"]="CLAIMED"; task["attempts"]+=1; task["state_history"].append("CLAIMED")
        task["lease"]={"owner":worker_id,"token":secrets.token_hex(16),"expires_at":stamp(now+timedelta(seconds=policy["timeout_seconds"]))}
        queue["revision"]+=1; atomic_write(queue_path,queue); return task

def complete_task(task_id,worker_id,lease_token,*,success,result=None,error=None,queue_path=QUEUE,registry_path=REGISTRY,now=None):
    now=now or now_utc()
    with queue_lock(queue_path):
        queue,by_id=context(queue_path,registry_path)
        task=next((t for t in queue["tasks"] if t.get("task_id")==task_id),None)
        if task is None: raise ValueError(f"unknown task_id: {task_id}")
        lease=task.get("lease")
        if task.get("status")!="CLAIMED" or not isinstance(lease,dict): raise ValueError("task is not currently claimed")
        if lease.get("owner")!=worker_id or not secrets.compare_digest(str(lease.get("token","")),str(lease_token)): raise ValueError("lease owner or token mismatch")
        if datetime.fromisoformat(lease["expires_at"].replace("Z","+00:00"))<=now: raise ValueError("lease has expired; recover the task before completing it")
        authorize(task,by_id)
        if success and not isinstance(result,dict): raise ValueError("successful completion requires a result object")
        if not success and not isinstance(error,dict): raise ValueError("failed completion requires an error object")
        task["lease"]=None
        if success:
            task["status"]="SUCCEEDED"; task["result"]=result; task["last_error"]=None; task["state_history"].append("SUCCEEDED")
        else:
            task["last_error"]=error; task["state_history"].append("FAILED")
            if task["attempts"]<task["max_attempts"]:
                task["status"]="QUEUED"; task["state_history"].append("QUEUED")
                task["not_before"]=stamp(now+timedelta(seconds=min(900,30*(2**max(0,task["attempts"]-1)))))
            else:
                task["status"]="DEAD_LETTER"; task["state_history"].append("DEAD_LETTER")
        queue["revision"]+=1; atomic_write(queue_path,queue); return task

def recover_expired(queue_path=QUEUE,registry_path=REGISTRY,now=None):
    now=now or now_utc(); recovered=[]
    with queue_lock(queue_path):
        queue,_=context(queue_path,registry_path)
        for task in queue["tasks"]:
            if task.get("status")!="CLAIMED": continue
            lease=task.get("lease") or {}
            if datetime.fromisoformat(lease["expires_at"].replace("Z","+00:00"))>now: continue
            task["lease"]=None; task["last_error"]={"type":"lease_expired","message":"Worker lease expired before completion."}
            if task["attempts"]<task["max_attempts"]:
                task["status"]="QUEUED"; task["state_history"].append("QUEUED")
                task["not_before"]=stamp(now+timedelta(seconds=min(900,30*(2**max(0,task["attempts"]-1)))))
            else:
                task["status"]="DEAD_LETTER"; task["state_history"].append("DEAD_LETTER")
            recovered.append(task)
        if recovered: queue["revision"]+=1; atomic_write(queue_path,queue)
    return recovered

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--queue",type=Path,default=QUEUE); parser.add_argument("--registry",type=Path,default=REGISTRY)
    subs=parser.add_subparsers(dest="command",required=True)
    en=subs.add_parser("enqueue"); en.add_argument("--task-json",type=Path,required=True)
    cl=subs.add_parser("claim"); cl.add_argument("--worker-id",required=True)
    subs.add_parser("recover-expired")
    args=parser.parse_args()
    try:
        if args.command=="enqueue": out=enqueue_task(read_json(args.task_json),args.queue,args.registry)
        elif args.command=="claim":
            task=claim_next(args.worker_id,args.queue,args.registry); out={"claimed":task is not None,"task":task}
        else:
            tasks=recover_expired(args.queue,args.registry); out={"recovered_count":len(tasks),"tasks":tasks}
        print(json.dumps(out,ensure_ascii=False)); return 0
    except ValueError as exc:
        print(f"TASK QUEUE RUNTIME ERROR: {exc}",file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
