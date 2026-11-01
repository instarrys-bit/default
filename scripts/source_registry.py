#!/usr/bin/env python3
"""Fail-closed validation for policy-labelled domain source registries."""
from __future__ import annotations
from urllib.parse import urlparse

POLICIES={"DIRECT","PROXY","REJECT"}
FORMATS={"domain-only","adblock-domain-rules","shadowrocket-domain-rules","quantumult-domain-rules"}
ROLES={"primary_candidate_source","independent_adblock_corroboration","independent_policy_corroboration"}
LINEAGE_STATES={"verified","partial","unverified"}

def validate_registry(config):
    sources=config.get("sources")
    scoring=config.get("scoring")
    if not isinstance(sources,list) or not sources or not isinstance(scoring,dict):
        raise ValueError("source registry or scoring configuration is missing")
    by_id={}
    for source in sources:
        if not isinstance(source,dict):
            raise ValueError("source registry entries must be objects")
        sid=str(source.get("id","")).strip()
        if not sid or sid in by_id:
            raise ValueError("source registry contains a missing or duplicate ID")
        by_id[sid]=source
        policy=str(source.get("classification","")).upper()
        if source.get("format") not in FORMATS:
            raise ValueError("source has an unsupported parser format: "+sid)
        if source.get("role") not in ROLES:
            raise ValueError("source has an unsupported collection role: "+sid)
        if source.get("lineage_status") not in LINEAGE_STATES:
            raise ValueError("source lineage_status must be verified, partial or unverified: "+sid)
        upstreams=source.get("upstream_repositories",[])
        if not isinstance(upstreams,list) or len(upstreams)!=len(set(upstreams)) or any(not isinstance(x,str) or not x.strip() for x in upstreams):
            raise ValueError("source upstream_repositories must be a unique list of repository names: "+sid)
        if source.get("lineage_status")=="verified" and not str(source.get("lineage_evidence_url","")).startswith("https://"):
            raise ValueError("verified source lineage requires a public evidence URL: "+sid)
        if source.get("format")!="domain-only" and source.get("allow_leading_dot",False):
            raise ValueError("allow_leading_dot is only valid for domain-only sources: "+sid)
        if policy not in POLICIES:
            raise ValueError("source has an unsupported policy classification: "+sid)
        if not str(source.get("publisher","")).strip():
            raise ValueError("source publisher is missing: "+sid)
        if not str(source.get("independence_group","")).strip():
            raise ValueError("source independence group is missing: "+sid)
        parsed=urlparse(str(source.get("url","")))
        if parsed.scheme!="https" or parsed.hostname!="raw.githubusercontent.com" or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError("source URL must be HTTPS raw.githubusercontent.com: "+sid)
        weight=float(source.get("weight",0))
        if not 0 < weight <= 1:
            raise ValueError("source weight must be greater than 0 and at most 1: "+sid)
    minimum=int(scoring.get("minimum_independent_sources",0))
    threshold=float(scoring.get("minimum_confidence",-1))
    if minimum<2 or not 0 < threshold <= 1:
        raise ValueError("invalid minimum independent-source or confidence threshold")
    weights=scoring.get("source_weights",{})
    if set(weights)!=set(by_id):
        raise ValueError("source weight map must exactly match configured source IDs")
    for sid,weight in weights.items():
        if abs(float(weight)-float(by_id[sid]["weight"]))>1e-9:
            raise ValueError("scoring weight does not match source registry: "+sid)
    required_by_policy=scoring.get("required_sources_by_policy",{})
    if set(required_by_policy)-POLICIES:
        raise ValueError("required source policy contains an unsupported class")
    for policy in POLICIES:
        required=required_by_policy.get(policy,[])
        if not isinstance(required,list) or len(required)!=len(set(required)):
            raise ValueError("required source IDs must be a unique list: "+policy)
        if any(sid not in by_id for sid in required):
            raise ValueError("required source ID is not configured: "+policy)
        if any(by_id[sid].get("enabled",True) is False for sid in required):
            raise ValueError("disabled source cannot be required for publication: "+policy)
        if any(str(by_id[sid].get("classification","")).upper()!=policy for sid in required):
            raise ValueError("required source policy does not match its declared classification: "+policy)
        policy_sources={sid for sid,source in by_id.items()
                        if source.get("enabled",True) is not False
                        and str(source.get("classification","")).upper()==policy}
        if policy_sources and not any(by_id[sid].get("role")=="primary_candidate_source" for sid in policy_sources):
            raise ValueError("enabled "+policy+" policy has no primary candidate source")
        if policy_sources and not policy_sources.issubset(set(required)):
            raise ValueError("all enabled "+policy+" sources must be explicitly required before they can authorize publication")
        if required:
            publishers={by_id[sid]["publisher"] for sid in required}
            groups={by_id[sid]["independence_group"] for sid in required}
            urls={by_id[sid]["url"] for sid in required}
            ancestry=[set(by_id[sid].get("upstream_repositories",[])) for sid in required]
            shared_upstream=any(ancestry[i] & ancestry[j] and by_id[required[i]].get("lineage_status")=="verified" and by_id[required[j]].get("lineage_status")=="verified" for i in range(len(ancestry)) for j in range(i+1,len(ancestry)))
            if len(required)<minimum or len(publishers)<minimum or len(groups)<minimum or len(urls)<minimum or shared_upstream:
                raise ValueError("required "+policy+" sources do not meet publisher/group/URL independence minimum or share a declared upstream")
            score=min(1.0,sum(float(weights[sid]) for sid in required))
            if score<threshold:
                raise ValueError("required "+policy+" source weights do not meet confidence threshold")
    return by_id
