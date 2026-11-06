#!/usr/bin/env python3
"""Fail-closed validation for registered execution adapter contracts."""
from __future__ import annotations

import argparse, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path,label):
    try: value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value,dict): raise ValueError(f"{label} must be an object")
    return value
def dispatch_contract(path):
    lines=path.read_text(encoding="utf-8").splitlines()
    start=next((i for i,x in enumerate(lines) if re.fullmatch(r"  workflow_dispatch:\s*(?:#.*)?",x)),None)
    if start is None: return False,[]
    end=next((i for i in range(start+1,len(lines)) if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$",lines[i])),len(lines))
    block=lines[start+1:end]
    inp=next((i for i,x in enumerate(block) if re.fullmatch(r"    inputs:\s*",x)),None)
    if inp is None: return True,[]
    found=[]
    for i,line in enumerate(block[inp+1:],inp+1):
        m=re.fullmatch(r"      ([A-Za-z_][A-Za-z0-9_-]*):\s*",line)
        if not m: continue
        e=next((j for j in range(i+1,len(block)) if re.match(r"^      [A-Za-z_][A-Za-z0-9_-]*:\s*$",block[j])),len(block))
        sub="\n".join(block[i+1:e])
        req=re.search(r"(?m)^        required:\s*(true|false)\s*$",sub)
        typ=re.search(r"(?m)^        type:\s*([A-Za-z_]+)\s*$",sub)
        if not req or not typ: raise ValueError(f"{path}: input {m.group(1)} must declare required and type")
        found.append({"name":m.group(1),"type":typ.group(1),"required":req.group(1)=="true"})
    return True,found
def has_task_correlation_run_name(path):
    content=path.read_text(encoding="utf-8")
    return bool(re.search(r"(?m)^run-name:.*\$\{\{\s*inputs\.automation_task_id\b",content))
def validate_execution_adapters(root=ROOT,adapters_path=None,registry_path=None):
    ap=Path(adapters_path) if adapters_path else root/"automation/execution_adapters.json"
    rp=Path(registry_path) if registry_path else root/"automation/program_registry.json"
    doc,reg=load(ap,"execution adapters"),load(rp,"program registry")
    if doc.get("schema_version")!=1: raise ValueError("unsupported execution adapter schema_version")
    pol=doc.get("policy")
    expected={"deny_by_default":True,"all_adapters_disabled_by_default":True,"shell_execution":"prohibited","protected_config":"No adapter may modify modules/uu.conf."}
    if not isinstance(pol,dict): raise ValueError("execution adapter policy must be an object")
    for k,v in expected.items():
        if pol.get(k)!=v: raise ValueError(f"policy {k} must equal {v!r}")
    for k in ("permission_rule","completion_rule"):
        if not isinstance(pol.get(k),str) or not pol[k].strip(): raise ValueError(f"policy {k} is required")
    programs,items=reg.get("programs"),doc.get("adapters")
    if not isinstance(programs,list) or not isinstance(items,list): raise ValueError("programs and adapters must be arrays")
    byid={p.get("id"):p for p in programs if isinstance(p,dict) and isinstance(p.get("id"),str)}
    adapters={}
    for a in items:
        if not isinstance(a,dict): raise ValueError("adapter entries must be objects")
        tid=a.get("target_program_id")
        if tid not in byid: raise ValueError(f"unknown adapter target {tid!r}")
        if tid in adapters: raise ValueError(f"duplicate adapter for {tid}")
        adapters[tid]=a
    if set(adapters)!=set(byid): raise ValueError(f"adapter inventory mismatch; missing={sorted(set(byid)-set(adapters))}, stale={sorted(set(adapters)-set(byid))}")
    for tid,p in byid.items():
        a=adapters[tid]; kind=p.get("kind"); orch=p.get("orchestration",{})
        if a.get("target_kind")!=kind: raise ValueError(f"{tid} target_kind mismatch")
        enabled=a.get("enabled")
        callers=a.get("allowed_callers")
        if not isinstance(enabled,bool): raise ValueError(f"{tid}.enabled must be boolean")
        if not isinstance(callers,list) or any(not isinstance(x,str) or not x for x in callers) or len(callers)!=len(set(callers)): raise ValueError(f"{tid}.allowed_callers invalid")
        if enabled!=(orch.get("enabled") is True) or callers!=orch.get("allowed_callers",[]): raise ValueError(f"{tid} adapter activation/callers must match registry orchestration")
        timeout=a.get("timeout_seconds")
        if isinstance(timeout,bool) or not isinstance(timeout,int) or not 1<=timeout<=3600: raise ValueError(f"{tid}.timeout_seconds invalid")
        retry=a.get("retry")
        attempts=retry.get("max_attempts") if isinstance(retry,dict) else None
        if isinstance(attempts,bool) or not isinstance(attempts,int) or not 0<=attempts<=orch.get("max_attempts",0): raise ValueError(f"{tid} retry budget exceeds orchestration policy")
        completion=a.get("completion")
        if not isinstance(completion,dict) or completion.get("independent_verification_required") is not True: raise ValueError(f"{tid} requires independent completion verification")
        resource_contract=a.get("resource_contract")
        if tid=="workflow_auto_sync" and enabled and resource_contract is None: raise ValueError("workflow_auto_sync requires an exclusive fenced resource_contract")
        if resource_contract is not None:
            if not isinstance(resource_contract,dict) or resource_contract.get("mode")!="exclusive" or resource_contract.get("fencing_required") is not True: raise ValueError(f"{tid} resource_contract must require exclusive fenced leases")
            keys=resource_contract.get("resource_keys")
            if not isinstance(keys,list) or not keys or any(not isinstance(k,str) or not k or k.startswith("/") or chr(92) in k or any(part in {"",".",".."} for part in k.split("/")) for k in keys) or len(keys)!=len(set(keys)): raise ValueError(f"{tid} resource_contract resource_keys invalid")
            seconds=resource_contract.get("lease_seconds")
            if isinstance(seconds,bool) or not isinstance(seconds,int) or not 1<=seconds<=21600: raise ValueError(f"{tid} resource_contract lease_seconds invalid")
        read_only=a.get("read_only_resources",[])
        if not isinstance(read_only,list) or any(not isinstance(path,str) or not path or path.startswith("/") or chr(92) in path or any(part in {"",".",".."} for part in path.split("/")) for path in read_only) or len(read_only)!=len(set(read_only)): raise ValueError(f"{tid} read_only_resources invalid")
        required_read_only=a.get("required_read_only_resources",[])
        if not isinstance(required_read_only,list) or any(path not in read_only for path in required_read_only) or len(required_read_only)!=len(set(required_read_only)): raise ValueError(f"{tid} required_read_only_resources must be a unique subset of read_only_resources")
        publish=a.get("publish_resources",[])
        write_resources=a.get("write_resources",[])
        resource_contract=a.get("resource_contract")
        resource_keys=resource_contract.get("resource_keys",[]) if isinstance(resource_contract,dict) else []
        if (not isinstance(write_resources,list) or len(write_resources)!=len(set(write_resources))
                or any(path not in resource_keys or path=="modules/uu.conf" for path in write_resources)): raise ValueError(f"{tid} write_resources must be a unique subset of exclusive non-config resource keys")
        if not isinstance(publish,list) or len(publish)!=len(set(publish)) or any(path not in write_resources for path in publish): raise ValueError(f"{tid} publish_resources must be a unique subset of write_resources")
        if publish:
            completion=a.get("completion",{})
            verifier=completion.get("artifact_verifier") if isinstance(completion,dict) else None
            output=a.get("output_contract")
            if not isinstance(verifier,dict) or not isinstance(output,dict) or "artifact_publication" not in output.get("required",[]): raise ValueError(f"{tid} publishing requires an independent verifier and artifact_publication output")
        if resource_contract is not None and set(read_only)&set(resource_contract.get("resource_keys",[])): raise ValueError(f"{tid} resource cannot be both read-only and writable")
        artifact_verifier=completion.get("artifact_verifier")
        if artifact_verifier is not None:
            if not isinstance(artifact_verifier,dict) or not isinstance(artifact_verifier.get("path"),str) or not artifact_verifier["path"].startswith("scripts/") or not isinstance(artifact_verifier.get("output_field"),str) or not artifact_verifier["output_field"] or not isinstance(artifact_verifier.get("program_id"),str): raise ValueError(f"{tid} artifact_verifier contract invalid")
            verifier_program=byid.get(artifact_verifier["program_id"])
            if not isinstance(verifier_program,dict) or verifier_program.get("path")!=artifact_verifier["path"] or verifier_program.get("kind")!="python_component": raise ValueError(f"{tid} artifact_verifier program identity mismatch")
            verifier_path=(root/artifact_verifier["path"]).resolve()
            if not verifier_path.is_relative_to(root.resolve()) or not verifier_path.is_file(): raise ValueError(f"{tid} artifact_verifier path is missing or outside repository")
            output=a.get("output_contract")
            if not isinstance(output,dict) or artifact_verifier["output_field"] not in output.get("properties",{}) or artifact_verifier["output_field"] not in output.get("required",[]): raise ValueError(f"{tid} output_contract must require the artifact_verifier output field")
        if kind=="python_component":
            ep=a.get("entrypoint")
            if a.get("adapter_type")!="python_cli" or a.get("interface_status") not in ("unreviewed","reviewed"): raise ValueError(f"{tid} Python adapter type/status invalid")
            if not isinstance(ep,dict) or ep.get("path")!=p.get("path") or ep.get("executable")!="python3" or ep.get("shell") is not False: raise ValueError(f"{tid} must use exact python3 entrypoint without shell")
            argv=ep.get("argv_template")
            if not isinstance(argv,list) or any(not isinstance(x,str) for x in argv): raise ValueError(f"{tid} argv_template invalid")
            if a["interface_status"]=="unreviewed" and (enabled or argv or a.get("input_contract") is not None or a.get("output_contract") is not None): raise ValueError(f"{tid} unreviewed Python adapter cannot execute")
            if a["interface_status"]=="reviewed" and (not isinstance(a.get("input_contract"),dict) or not isinstance(a.get("output_contract"),dict)): raise ValueError(f"{tid} reviewed adapter requires input/output contracts")
        elif kind=="github_actions_workflow":
            w=a.get("workflow")
            if a.get("adapter_type")!="github_actions_workflow" or not isinstance(w,dict) or w.get("path")!=p.get("path"): raise ValueError(f"{tid} workflow adapter/path invalid")
            actual,inputs=dispatch_contract(root/p["path"])
            if w.get("dispatchable") is not actual or w.get("inputs")!=inputs: raise ValueError(f"{tid} workflow_dispatch contract drift")
            if actual and ("automation_task_id" not in {item["name"] for item in inputs} or not has_task_correlation_run_name(root/p["path"])):
                raise ValueError(f"{tid} requires automation_task_id input and a correlated run-name")
            if a.get("interface_status")!=("workflow_dispatch_reviewed" if actual else "event_only"): raise ValueError(f"{tid} workflow interface_status invalid")
            if not isinstance(w.get("allowed_refs"),list) or not w["allowed_refs"]: raise ValueError(f"{tid} allowed_refs must be explicit")
            if not isinstance(w.get("caller_permissions_required"),list) or not {"actions:write","issues:write"}.issubset(set(w["caller_permissions_required"])): raise ValueError(f"{tid} caller requires actions:write and issues:write")
            if enabled and not actual: raise ValueError(f"{tid} event-only workflow cannot be dispatched")
        else: raise ValueError(f"{tid} unsupported target kind")
        if not enabled and callers: raise ValueError(f"{tid} disabled adapter cannot allow callers")
        if enabled and not callers: raise ValueError(f"{tid} enabled adapter requires callers")
    return {"valid":True,"adapter_count":len(items),"python_adapter_count":sum(a.get("target_kind")=="python_component" for a in items),"workflow_adapter_count":sum(a.get("target_kind")=="github_actions_workflow" for a in items),"enabled_adapter_count":sum(a.get("enabled") is True for a in items)}
def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--root",type=Path,default=ROOT); parser.add_argument("--adapters",type=Path); parser.add_argument("--registry",type=Path); args=parser.parse_args()
    try: result=validate_execution_adapters(args.root,args.adapters,args.registry)
    except ValueError as exc: print(f"EXECUTION ADAPTERS INVALID: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
