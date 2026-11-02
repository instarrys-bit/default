#!/usr/bin/env python3
"""Continuously audit declared source ancestry against public provenance documents.

This inventories repository references and shared upstreams. It deliberately does
not promote a source to verified: publisher-level source lists are not item-level
domain provenance.
"""
from __future__ import annotations
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from json_document_store import read_document
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources/domain_sources.json"
OUTPUT = ROOT / "reports/source-lineage-audit.json"
DISCOVERY = ROOT / "sources/discovered_sources.json"
MAX_BYTES = 4_000_000
GH_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:github\.com|raw\.githubusercontent\.com)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)
OTHER_RE = re.compile(r"https?://(codeberg\.org|gitlab\.com)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)
PETER_LOWE_RE = re.compile(r"pgl\.yoyo\.org|peter.?lowe", re.I)
RESERVED_GITHUB_PATHS = {"repos", "orgs", "users", "topics", "sponsors"}

def raw_evidence_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != "github.com":
        raise ValueError("lineage evidence URL must be an HTTPS GitHub file URL: " + url)
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 5 or parts[2] not in ("blob", "raw"):
        raise ValueError("lineage evidence URL must identify a GitHub file: " + url)
    owner, repo, _, branch = parts[:4]
    path = "/".join(parts[4:])
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

def fetch_text(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-Source-Lineage-Audit/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise ValueError("unexpected lineage evidence response: " + response.geturl())
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("lineage evidence document exceeds size limit: " + url)
    return data

def extract_upstreams(text: str) -> set[str]:
    found = set()
    for owner, repo in GH_RE.findall(text):
        if owner.lower() not in RESERVED_GITHUB_PATHS:
            found.add(f"{owner.lower()}/{repo.lower().removesuffix('.git')}")
    for host, owner, repo in OTHER_RE.findall(text):
        prefix = "codeberg:" if host.lower() == "codeberg.org" else "gitlab:"
        found.add(prefix + owner.lower() + "/" + repo.lower().removesuffix(".git"))
    if PETER_LOWE_RE.search(text):
        found.add("peter-lowe")
    return found

def normalize_upstream(value: str) -> str:
    value = str(value).strip().lower()
    if "peter-lowe" in value or "pgl.yoyo.org" in value:
        return "peter-lowe"
    return value


def shared_reference_pairs(records: list[dict], values_key: str, required_status: str) -> list[dict]:
    """Return only record pairs sharing references, using an inverted index."""
    inverted: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        if record.get("status") != required_status:
            continue
        for value in set(str(x) for x in record.get(values_key, [])):
            inverted.setdefault(value, []).append(index)
    overlaps: dict[tuple[int, int], set[str]] = {}
    for value, indexes in inverted.items():
        for position, left in enumerate(indexes):
            for right in indexes[position + 1:]:
                overlaps.setdefault((left, right), set()).add(value)
    return [
        {"left": left, "right": right, "shared": sorted(values)}
        for (left, right), values in sorted(overlaps.items())
    ]

def audit_registry(config: dict, fetcher=fetch_text, candidates: list[dict] | None = None, previous_report: dict | None = None) -> dict:
    sources = config.get("sources", [])
    inventories = []
    for source in sources:
        sid = source.get("id", "unknown")
        evidence_url = source.get("lineage_evidence_url", "")
        publisher = str(source.get("publisher", "")).lower()
        if not evidence_url:
            inventories.append({
                "source_id": sid,
                "publisher": publisher,
                "lineage_status": source.get("lineage_status", "unverified"),
                "evidence_url": None,
                "status": "missing_evidence_url",
                "error": "source has no public lineage evidence URL",
            })
            continue
        try:
            raw_url = raw_evidence_url(evidence_url)
            payload = fetcher(raw_url)
            text = payload.decode("utf-8-sig", errors="replace")
        except (OSError, ValueError, UnicodeError) as exc:
            inventories.append({
                "source_id": sid,
                "publisher": publisher,
                "lineage_status": source.get("lineage_status", "unverified"),
                "evidence_url": evidence_url,
                "status": "evidence_unavailable",
                "error": str(exc)[:500],
            })
            continue
        discovered = extract_upstreams(text)
        declared_raw = {str(x).lower() for x in source.get("upstream_repositories", [])}
        # Ignore the configured publisher itself when treating references as upstreams.
        discovered.discard(publisher)
        declared = {normalize_upstream(x) for x in declared_raw}
        discovered = {normalize_upstream(x) for x in discovered}
        comparison_upstreams = declared | discovered
        inventories.append({
            "source_id": sid,
            "publisher": publisher,
            "lineage_status": source.get("lineage_status", "unverified"),
            "evidence_url": evidence_url,
            "fetched_url": raw_url,
            "evidence_sha256": hashlib.sha256(payload).hexdigest(),
            "evidence_bytes": len(payload),
            "declared_upstream_count": len(declared),
            "discovered_upstream_count": len(discovered),
            "declared_upstreams": sorted(declared),
            "declared_and_discovered": sorted(declared & discovered),
            "declared_not_in_document": sorted(declared - discovered),
            "discovered_not_registered": sorted(discovered - declared),
            "discovered_upstreams": sorted(discovered),
            "comparison_upstreams": sorted(comparison_upstreams),
            "status": "audited"
        })
    candidate_docs = []
    previous_candidate_docs = {str(x.get("repository")): x for x in (previous_report or {}).get("candidate_sources", []) if x.get("repository")}
    for candidate in candidates or []:
        repository = str(candidate.get("repository", ""))
        if not repository or not candidate.get("rule_list_urls"):
            continue
        parts = repository.split("/", 1)
        if len(parts) != 2:
            continue
        owner, repo = parts
        branch = str(candidate.get("default_branch") or "main")
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        cached = previous_candidate_docs.get(repository)
        discovery_hash = str(candidate.get("readme_sha256") or "")
        if (cached and cached.get("status") == "audited_reference_inventory"
                and discovery_hash and cached.get("readme_sha256") == discovery_hash
                and cached.get("readme_url") == readme_url):
            candidate_docs.append({**cached, "discovery_readme_sha256": discovery_hash, "readme_changed_since_discovery": False})
            continue
        try:
            payload = fetcher(readme_url)
            readme = payload.decode("utf-8-sig", errors="replace")
            discovered_refs = extract_upstreams(readme)
            discovered_refs.discard(repository.lower())
            readme_hash = hashlib.sha256(payload).hexdigest()
            candidate_docs.append({
                "repository": repository,
                "readme_url": readme_url,
                "readme_sha256": readme_hash,
                "discovery_readme_sha256": discovery_hash or None,
                "readme_changed_since_discovery": bool(discovery_hash and discovery_hash != readme_hash),
                "referenced_repositories": sorted(discovered_refs),
                "reference_count": len(discovered_refs),
                "lineage_status": "unverified",
                "status": "audited_reference_inventory",
            })
        except (OSError, ValueError, UnicodeError) as exc:
            candidate_docs.append({
                "repository": repository,
                "readme_url": readme_url,
                "lineage_status": "unverified",
                "status": "readme_unavailable",
                "error": str(exc),
                "referenced_repositories": [],
                "reference_count": 0,
            })
    candidate_shared = [
        {
            "repositories": [candidate_docs[pair["left"]]["repository"], candidate_docs[pair["right"]]["repository"]],
            "shared_readme_references": pair["shared"],
            "interpretation": "Possible shared reference only; README hyperlinks do not prove actual rule-data ancestry."
        }
        for pair in shared_reference_pairs(candidate_docs, "referenced_repositories", "audited_reference_inventory")
    ]
    shared = [
        {
            "sources": [inventories[pair["left"]]["source_id"], inventories[pair["right"]]["source_id"]],
            "shared_upstreams": pair["shared"],
        }
        for pair in shared_reference_pairs(inventories, "comparison_upstreams", "audited")
    ]
    return {
        "schema_version": 1,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "method": "public-provenance-document repository-link inventory; not item-level domain attribution",
        "source_count": len(sources),
        "audited_source_count": sum(1 for x in inventories if x.get("status") == "audited"),
        "lineage_verified_count": sum(1 for x in sources if x.get("lineage_status") == "verified"),
        "lineage_partial_count": sum(1 for x in sources if x.get("lineage_status") == "partial"),
        "lineage_unverified_count": sum(1 for x in sources if x.get("lineage_status") == "unverified"),
        "shared_upstream_pairs": shared,
        "candidate_source_count": len(candidate_docs),
        "candidate_readme_audited_count": sum(1 for x in candidate_docs if x.get("status") == "audited_reference_inventory"),
        "candidate_shared_reference_pairs": candidate_shared,
        "candidate_sources": candidate_docs,
        "sources": inventories,
        "publication_rule": "This report never upgrades lineage_status. Only independently reviewed, complete item-level provenance can qualify a source as verified."
    }

def main():
    config = json.loads(REGISTRY.read_text(encoding="utf-8"))
    candidates = read_document(DISCOVERY, "candidates", {"candidates": []}).get("candidates", [])
    previous_report = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    report = audit_registry(config, candidates=candidates, previous_report=previous_report)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "audited_sources": report["audited_source_count"],
        "shared_upstream_pairs": len(report["shared_upstream_pairs"]),
        "lineage_verified": report["lineage_verified_count"],
        "lineage_partial": report["lineage_partial_count"],
        "lineage_unverified": report["lineage_unverified_count"]
    }, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
