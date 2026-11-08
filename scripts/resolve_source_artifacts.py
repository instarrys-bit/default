#!/usr/bin/env python3
"""Resolve exact, immutable Discovery and Assessment artifacts for production."""
from __future__ import annotations
import hashlib, io, json, os, shutil, sys, tempfile, urllib.request, zipfile
from pathlib import Path, PurePosixPath

API="https://api.github.com"
LIMIT=50_000_000

def request(url, token, limit=5_000_000):
    req=urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,"X-GitHub-Api-Version":"2022-11-28","User-Agent":"Shadowrocket-Source-Handoff/1.0"})
    with urllib.request.urlopen(req,timeout=60) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError("GitHub response exceeds size limit")
    return data

def download_archive(url, token):
    import urllib.error
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    req=urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,"X-GitHub-Api-Version":"2022-11-28","User-Agent":"Shadowrocket-Source-Handoff/1.0"})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        response=opener.open(req,timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code not in {301,302,303,307,308}:
            raise
        location=exc.headers.get("Location")
        if not location:
            raise ValueError("GitHub artifact redirect has no signed location")
        response=urllib.request.urlopen(urllib.request.Request(location,headers={"User-Agent":"Shadowrocket-Source-Handoff/1.0"}),timeout=60)
    with response:
        data=response.read(LIMIT+1)
    if len(data)>LIMIT: raise ValueError("Actions artifact archive exceeds size limit")
    return data

def api_json(url,token):
    value=json.loads(request(url,token).decode("utf-8"))
    if not isinstance(value,dict): raise ValueError("GitHub API response is not an object")
    return value

def extract(data,destination):
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members=archive.infolist()
        if not members or len(members)>5000: raise ValueError("invalid artifact member count")
        for member in members:
            name=member.filename.replace("\\","/")
            p=PurePosixPath(name)
            if p.is_absolute() or any(x in {"",".",".."} for x in p.parts): raise ValueError("unsafe artifact path")
            if ((member.external_attr>>16)&0o170000)==0o120000: raise ValueError("artifact symlink rejected")
            target=destination.joinpath(*p.parts)
            if member.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
            target.parent.mkdir(parents=True,exist_ok=True)
            payload=archive.read(member)
            if len(payload)>LIMIT: raise ValueError("artifact member too large")
            target.write_bytes(payload)
    return destination

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def unique(root,name):
    hits=list(root.rglob(name))
    if len(hits)!=1: raise ValueError("expected exactly one "+name)
    return hits[0]

def verify_manifest(root,proof,name):
    files=proof.get("files")
    if not isinstance(files,list) or not files: raise ValueError("missing artifact file manifest")
    expected={}
    for row in files:
        rel=row.get("path") if isinstance(row,dict) else None
        sha=row.get("sha256") if isinstance(row,dict) else None
        p=PurePosixPath(rel or "")
        if not isinstance(sha,str) or len(sha)!=64 or p.is_absolute() or any(x in {"",".",".."} for x in p.parts) or rel==name: raise ValueError("invalid artifact manifest entry")
        expected[rel]=sha
    actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name!=name}
    if actual!=set(expected): raise ValueError("artifact file set differs from proof")
    for rel,sha in expected.items():
        if digest(root.joinpath(*PurePosixPath(rel).parts))!=sha: raise ValueError("artifact file digest mismatch: "+rel)
    manifest_sha=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if proof.get("artifact_sha256")!=manifest_sha: raise ValueError("artifact manifest digest mismatch")

def download_artifact(repo,run_id,name,token,dest):
    meta=api_json(f"{API}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",token)
    found=[x for x in meta.get("artifacts",[]) if x.get("name")==name and x.get("expired") is False and str((x.get("workflow_run") or {}).get("id"))==str(run_id)]
    if len(found)!=1: raise ValueError(f"run {run_id}: expected one unexpired {name}")
    item=found[0]
    if not 0<int(item.get("size_in_bytes",0))<=LIMIT: raise ValueError("artifact size outside limit")
    data=download_archive(item["archive_download_url"],token)
    return extract(data,dest),item

def resolve_task(queue):
    tasks=queue.get("tasks")
    if not isinstance(tasks,list): raise ValueError("queue tasks missing")
    discoveries=[t for t in tasks if isinstance(t,dict) and t.get("target_program_id")=="workflow_source_discovery"]
    latest=max(discoveries,key=lambda t:(str(t.get("created_at","")),str(t.get("task_id",""))),default=None)
    if not latest or latest.get("status")!="SUCCEEDED" or (latest.get("verification") or {}).get("status")!="passed": raise ValueError("latest Discovery is not verified SUCCEEDED")
    run_id=(latest.get("result") or {}).get("run_evidence",{}).get("run_id")
    if isinstance(run_id,bool) or not isinstance(run_id,int) or run_id<=0: raise ValueError("Discovery run ID missing")
    from source_handoff_policy import classify_assessment_handoff
    if classify_assessment_handoff(tasks,str(run_id)).get("state")!="already_assessed": raise ValueError("latest Discovery has no verified Assessment")
    candidates=[t for t in tasks if isinstance(t,dict) and t.get("target_program_id")=="script_assess_sources" and str(((t.get("input") or {}).get("predecessor") or {}).get("workflow_run_id",""))==str(run_id) and t.get("status")=="SUCCEEDED" and (t.get("verification") or {}).get("status")=="passed" and ((t.get("result") or {}).get("artifact_verification") or {}).get("valid") is True and ((t.get("result") or {}).get("artifact_verification") or {}).get("activation_count")==0]
    if not candidates: raise ValueError("no verified Assessment matches latest Discovery")
    task=max(candidates,key=lambda t:(str(t.get("updated_at","")),str(t.get("task_id",""))))
    pred=(task.get("input") or {}).get("predecessor")
    if not isinstance(pred,dict) or pred.get("artifact_path")!="sources/discovered_sources.json": raise ValueError("Assessment predecessor is invalid")
    return task,pred

def main():
    if len(sys.argv)!=3: raise SystemExit("usage: resolve_source_artifacts.py QUEUE_JSON RUNNER_TEMP_DIR")
    repo=os.environ.get("GITHUB_REPOSITORY",""); token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    runner=Path(os.environ.get("RUNNER_TEMP",tempfile.gettempdir())).resolve(); dest=Path(sys.argv[2]).resolve()
    if not token or "/" not in repo or not dest.is_relative_to(runner) or dest==runner: raise SystemExit("missing GitHub auth/repository or unsafe temp path")
    dest.mkdir(parents=True,exist_ok=True)
    try:
        queue=json.loads(Path(sys.argv[1]).read_text())
        task,pred=resolve_task(queue)
        discovery,_=download_artifact(repo,str(pred["workflow_run_id"]),"source-discovery-output",token,dest/("discovery-"+str(pred["workflow_run_id"])))
        dp=unique(discovery,"source-discovery-proof.json"); proof=json.loads(dp.read_text())
        expected={"workflow_name":pred["workflow_name"],"workflow_run_id":str(pred["workflow_run_id"]),"workflow_head_sha":pred["workflow_head_sha"],"artifact_path":pred["artifact_path"]}
        if any(proof.get(k)!=v for k,v in expected.items()) or proof.get("artifact_sha256")!=pred["artifact_sha256"]: raise ValueError("Discovery proof does not match Assessment predecessor")
        from json_document_store import read_document
        from task_scheduler import read_only_resource_digests
        discovery_doc=dp.parent/"sources/discovered_sources.json"
        if not discovery_doc.is_file(): discovery_doc=unique(discovery,"discovered_sources.json")
        discovery_root=discovery_doc.parent.parent
        if read_only_resource_digests(discovery_root,["sources/discovered_sources.json"])["sources/discovered_sources.json"]!=pred["artifact_sha256"]: raise ValueError("Discovery logical document digest mismatch")
        runs=[]
        url=f"{API}/repos/{repo}/actions/workflows/automation-watchdog.yml/runs?branch=main&per_page=100"
        for page in range(1,6):
            batch=api_json(url+f"&page={page}",token).get("workflow_runs",[])
            runs.extend(batch)
            if len(batch)<100: break
        matches=[]
        for run in runs:
            if run.get("head_branch")!="main" or run.get("status")!="completed" or run.get("conclusion")!="success" or run.get("path")!=".github/workflows/automation-watchdog.yml": continue
            rid=str(run.get("id",""))
            if not rid.isdigit(): continue
            try:
                root,_=download_artifact(repo,rid,"source-assessment-output",token,dest/("assessment-"+rid))
                ap=unique(root,"source-assessment-proof.json"); assessment_proof=json.loads(ap.read_text())
                if (assessment_proof.get("assessment_task_id")!=task.get("task_id") or assessment_proof.get("predecessor")!=pred or assessment_proof.get("producer_workflow_path")!=".github/workflows/automation-watchdog.yml" or str(assessment_proof.get("producer_workflow_run_id"))!=rid or assessment_proof.get("producer_workflow_head_sha")!=run.get("head_sha") or assessment_proof.get("task_status")!="SUCCEEDED" or assessment_proof.get("verification_status")!="passed" or (assessment_proof.get("artifact_verification") or {}).get("valid") is not True or (assessment_proof.get("artifact_verification") or {}).get("activation_count")!=0):
                    shutil.rmtree(root,ignore_errors=True); continue
                verify_manifest(root,assessment_proof,"source-assessment-proof.json")
                matches.append((root,rid,assessment_proof["artifact_sha256"]))
            except Exception:
                continue
        if len(matches)!=1: raise ValueError(f"expected one verified Assessment artifact for task {task.get('task_id')}; found {len(matches)}")
        assessment_root,assessment_run_id,assessment_digest=matches[0]
        for rel,key in [("data/source_assessments_runtime.json","assessments"),("sources/source_assessments.json","assessments")]:
            path=assessment_root/rel
            if not path.exists() and not path.with_name(path.name+".manifest.json").exists(): raise ValueError("Assessment artifact missing "+rel)
            read_document(path,key,{key:[]})
        report=assessment_root/"reports/source-assessment.md"
        if not report.is_file() or report.stat().st_size==0: raise ValueError("Assessment report missing")
        with open(os.environ["GITHUB_ENV"],"a") as env:
            env.write(f"AUTOMATION_SOURCE_DISCOVERY_ROOT={discovery_root}\nAUTOMATION_SOURCE_ASSESSMENT_ROOT={assessment_root}\n")
            env.write(f"AUTOMATION_SOURCE_DISCOVERY_RUN_ID={pred['workflow_run_id']}\nAUTOMATION_SOURCE_ASSESSMENT_RUN_ID={assessment_run_id}\n")
            env.write(f"AUTOMATION_SOURCE_ASSESSMENT_TASK_ID={task['task_id']}\nAUTOMATION_SOURCE_DISCOVERY_SHA256={pred['artifact_sha256']}\nAUTOMATION_SOURCE_ASSESSMENT_SHA256={assessment_digest}\n")
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as summary:
            summary.write("### Verified independent source handoff\n\n")
            summary.write(f"- Discovery run: {pred['workflow_run_id']}\n- Assessment task: {task['task_id']}\n- Assessment artifact run: {assessment_run_id}\n- Both immutable artifacts passed provenance and content checks.\n")
        print(json.dumps({"valid":True,"discovery_run_id":pred["workflow_run_id"],"assessment_task_id":task["task_id"],"assessment_run_id":assessment_run_id,"assessment_sha256":assessment_digest},sort_keys=True))
        return 0
    except Exception as exc:
        print("SOURCE HANDOFF BLOCKED: "+str(exc),file=sys.stderr); return 1

if __name__=="__main__": raise SystemExit(main())
