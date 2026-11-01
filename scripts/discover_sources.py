#!/usr/bin/env python3
"""Discover candidate GitHub repositories without activating any source."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sources/discovered_sources.json"
REPORT = ROOT / "reports/source-discovery.md"
MAX_README_BYTES = 600_000
MAX_REPOS_PER_QUERY = 25
MAX_README_REPOSITORIES = 60
QUERIES = [
    "shadowrocket rules",
    "China domain list",
    "proxy domain list",
    "direct domain list",
    "geosite domain",
    "adblock domain list",
    "China direct domain rules list",
    "GFW proxy domain rules list",
    "Surge direct proxy domain-set rules",
    "Quantumult X direct proxy domain rules",
]
LIST_EXTENSIONS = (".list", ".txt", ".conf")
SEED_SOURCE_URLS = {
    "Hackl0us/SS-Rule-Snippet": [
        "https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/CN.list",
        "https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/foreign.list",
    ],
    "sve1r/Rules-For-Quantumult-X": [
        "https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/China.list",
        "https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list",
    ],
    "ACL4SSR/ACL4SSR": [
        "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list",
        "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list",
        "https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list",
    ],
    "blackmatrix7/ios_rule_script": [
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/China/China.list",
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Global/Global.list",
    ],
    "Loyalsoldier/v2ray-rules-dat": [
        "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/direct-list.txt",
        "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/proxy-list.txt",
        "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/reject-list.txt",
    ],
    "Jovanykoch/rules": [
        "https://raw.githubusercontent.com/Jovanykoch/rules/rel/loc-cn.list",
        "https://raw.githubusercontent.com/Jovanykoch/rules/rel/gfw.list",
        "https://raw.githubusercontent.com/Jovanykoch/rules/rel/reject.list",
    ],
    "gatework/surge-rules": [
        "https://raw.githubusercontent.com/gatework/surge-rules/release/direct.txt",
        "https://raw.githubusercontent.com/gatework/surge-rules/release/proxy.txt",
        "https://raw.githubusercontent.com/gatework/surge-rules/release/gfw.txt",
    ],
    "Clash-FX/cn-apps-direct-domains": [
        "https://raw.githubusercontent.com/Clash-FX/cn-apps-direct-domains/main/apps-direct-domains.list",
    ],
}
SENSITIVE_PATH_RE = re.compile(r"(?:porn|adult|nsfw|xxx|sex[-_]?content)", re.I)
RELEVANCE_RE = re.compile(r"(?:shadowrocket|domain|geosite|rules?|blocklist|adblock|dns|proxy|direct|china|gfw|clash|sing[-_]?box|v2ray|surge|loon|quantumult|hosts)", re.I)

def request_json(url: str, token: str = "") -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Shadowrocket-Deterministic-Source-Discovery/1.0",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise ValueError("GitHub API returned HTTP " + str(response.status))
        return json.loads(response.read(2_000_000).decode("utf-8"))

def fetch_readme(owner: str, repo: str, branch: str) -> str:
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) for x in (owner, repo, branch)):
        return ""
    for filename in ("README.md", "readme.md", "README.rst"):
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
        req = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-Source-Discovery/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                final = urllib.parse.urlparse(response.geturl())
                if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
                    continue
                payload = response.read(MAX_README_BYTES + 1)
                if len(payload) > MAX_README_BYTES:
                    continue
                return payload.decode("utf-8-sig", errors="replace")
        except (OSError, urllib.error.URLError):
            continue
    return ""

def extract_list_urls(text: str, owner: str, repo: str, branch: str) -> list[str]:
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) for x in (owner, repo, branch)):
        return []
    pattern = re.compile(
        r"https?://(?:raw\.githubusercontent\.com|github\.com)/"
        + re.escape(owner) + "/" + re.escape(repo)
        + r"/(?:blob/)?"
        + re.escape(branch) + r"/[^\s<>\]\[()\"']+",
        re.I,
    )
    found = set()
    for match in pattern.findall(text):
        url = match.rstrip(".,;:")
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        parts = [x for x in path.split("/") if x]
        if parsed.hostname == "github.com":
            if len(parts) < 5 or parts[2] != "blob":
                continue
            if parts[0].lower() != owner.lower() or parts[1].lower() != repo.lower() or parts[3] != branch:
                continue
            path = "/" + "/".join(parts[4:])
        elif parsed.hostname == "raw.githubusercontent.com":
            if len(parts) < 4 or parts[0].lower() != owner.lower() or parts[1].lower() != repo.lower() or parts[2] != branch:
                continue
            path = "/" + "/".join(parts[3:])
        else:
            continue
        if not path.lower().endswith(LIST_EXTENSIONS):
            continue
        if SENSITIVE_PATH_RE.search(path):
            continue
        clean_path = urllib.parse.unquote(path)
        if any(part in ("..", ".") for part in clean_path.split("/")):
            continue
        found.add(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}{clean_path}")
    return sorted(found)

def is_relevant_candidate(item: dict) -> bool:
    if item.get("rule_list_urls"):
        return True
    searchable = " ".join([str(item.get("repository", "")), str(item.get("description") or "")])
    return bool(RELEVANCE_RE.search(searchable))

def extract_readme_policy_claims(readme: str, urls: list[str]) -> dict:
    claims = {}
    for url in urls:
        actions = set()
        escaped = re.escape(url)
        for match in re.finditer(
            r"RULE-SET\s*,\s*" + escaped + r"\s*,\s*(DIRECT|PROXY|REJECT)\b",
            readme, re.I
        ):
            actions.add(match.group(1).upper())
        basename = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1].lower()
        stem = basename.rsplit(".", 1)[0] if basename else ""
        for line in readme.splitlines():
            lower = line.lower()
            if not basename or (basename not in lower and (not stem or stem not in lower)):
                continue
            if "规则碎片-直连" in line or "直连" in line or re.search(r"\bdirect\b", lower):
                actions.add("DIRECT")
            if "规则碎片-代理" in line or "代理" in line or re.search(r"\bproxy\b", lower):
                actions.add("PROXY")
            if "规则碎片-拦截" in line or "拦截" in line or re.search(r"\b(reject|block(?:ed)?[- ]?list|advertising|adblock|ads)\b", lower):
                actions.add("REJECT")
        if actions:
            claims[url] = sorted(actions)
    return claims

def merge_candidates(existing: dict, discovered: list[dict]) -> dict:
    prior = {
        x["repository"]: x for x in existing.get("candidates", [])
        if x.get("repository") and is_relevant_candidate(x)
    }
    for item in discovered:
        key = item["repository"]
        old = prior.get(key)
        if old:
            item["discovered_at"] = old.get("discovered_at", item["discovered_at"])
            item["search_queries"] = sorted(set(old.get("search_queries", [])) | set(item.get("search_queries", [])))
            item["rule_list_urls"] = sorted(set(old.get("rule_list_urls", [])) | set(item.get("rule_list_urls", [])))
            item["seeded_source_urls"] = sorted(set(old.get("seeded_source_urls", [])) | set(item.get("seeded_source_urls", [])))
            prior_claims = old.get("readme_policy_claims", {})
            current_claims = item.get("readme_policy_claims", {})
            item["readme_policy_claims"] = {
                url: sorted(set(prior_claims.get(url, [])) | set(current_claims.get(url, [])))
                for url in set(prior_claims) | set(current_claims)
            }
        item["rule_list_urls"] = [
            url for url in item.get("rule_list_urls", [])
            if not SENSITIVE_PATH_RE.search(urllib.parse.urlparse(url).path)
        ]
        if is_relevant_candidate(item):
            prior[key] = item
    return {
        "schema_version": 1,
        "discovery_queries": QUERIES,
        "candidate_count": len(prior),
        "candidates": [prior[key] for key in sorted(prior)],
        "activation_policy": "Discovery never adds or enables a source in sources/domain_sources.json.",
    }

def render_report(data: dict) -> str:
    rows = [
        "# Automated source discovery",
        "",
        f"- Candidate repositories retained: **{data['candidate_count']}**",
        "- Discovery is a lead-generation stage only; no candidate is activated automatically.",
        "- Search-query labels are not policy evidence. China/geosite labels do not imply DIRECT; proxy/GFW labels do not imply PROXY.",
        "",
        "## Candidate repositories",
        "",
    ]
    for item in data["candidates"]:
        rows.append(f"### [{item['repository']}]({item['html_url']})")
        rows.append("")
        rows.append(f"- Description: {item.get('description') or 'Not supplied'}")
        rows.append(f"- Stars: {item.get('stars', 0)}; archived: {item.get('archived', False)}; fork: {item.get('fork', False)}")
        rows.append(f"- Search queries: {', '.join(item.get('search_queries', [])) or '—'}")
        rows.append(f"- README / curated seed rule-list links: {len(item.get('rule_list_urls', []))}")
        rows.append(f"- Curated seed links: {len(item.get('seeded_source_urls', []))}")
        for url in item.get("rule_list_urls", []):
            rows.append(f"  - {url}")
        rows.append("")
    rows.extend([
        "## Activation requirements",
        "",
        "A discovered repository must pass source-level policy-semantics review, parser validation, publisher identity checks, lineage/overlap analysis, update-drift checks, and the configured evidence threshold before it can be registered as an active source.",
        "This report does not classify domains and does not alter DIRECT, PROXY, REJECT, DNS, MITM, or the user-managed Shadowrocket config.",
        "",
    ])
    return "\n".join(rows)

def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"candidates": []}
    discovered: dict[str, dict] = {}
    try:
        for query in QUERIES:
            params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": MAX_REPOS_PER_QUERY})
            result = request_json("https://api.github.com/search/repositories?" + params, token)
            for repo_data in result.get("items", []):
                full_name = str(repo_data.get("full_name", ""))
                if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
                    continue
                owner, name = full_name.split("/", 1)
                if full_name not in discovered:
                    branch = str(repo_data.get("default_branch") or "main")
                    readme = fetch_readme(owner, name, branch) if len(discovered) < MAX_README_REPOSITORIES else ""
                    discovered[full_name] = {
                        "repository": full_name,
                        "html_url": "https://github.com/" + full_name,
                        "description": repo_data.get("description"),
                        "default_branch": branch,
                        "updated_at": repo_data.get("updated_at"),
                        "pushed_at": repo_data.get("pushed_at"),
                        "stars": int(repo_data.get("stargazers_count") or 0),
                        "archived": bool(repo_data.get("archived")),
                        "fork": bool(repo_data.get("fork")),
                        "license": (repo_data.get("license") or {}).get("spdx_id") if isinstance(repo_data.get("license"), dict) else None,
                        "readme_sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest() if readme else None,
                        "rule_list_urls": extract_list_urls(readme, owner, name, branch),
                        "readme_policy_claims": {},
                        "search_queries": [],
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                    }
                    discovered[full_name]["readme_policy_claims"] = extract_readme_policy_claims(
                        readme, discovered[full_name]["rule_list_urls"]
                    )
                discovered[full_name]["search_queries"].append(query)

        for full_name, seed_urls in SEED_SOURCE_URLS.items():
            owner, name = full_name.split("/", 1)
            if full_name not in discovered:
                repo_data = request_json("https://api.github.com/repos/" + full_name, token)
                branch = str(repo_data.get("default_branch") or "main")
                readme = fetch_readme(owner, name, branch)
                discovered[full_name] = {
                    "repository": full_name,
                    "html_url": "https://github.com/" + full_name,
                    "description": repo_data.get("description"),
                    "default_branch": branch,
                    "updated_at": repo_data.get("updated_at"),
                    "pushed_at": repo_data.get("pushed_at"),
                    "stars": int(repo_data.get("stargazers_count") or 0),
                    "archived": bool(repo_data.get("archived")),
                    "fork": bool(repo_data.get("fork")),
                    "license": (repo_data.get("license") or {}).get("spdx_id") if isinstance(repo_data.get("license"), dict) else None,
                    "readme_sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest() if readme else None,
                    "rule_list_urls": extract_list_urls(readme, owner, name, branch),
                    "readme_policy_claims": {},
                    "seeded_source_urls": [],
                    "search_queries": ["curated_seed"],
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                }
                discovered[full_name]["readme_policy_claims"] = extract_readme_policy_claims(
                    readme, discovered[full_name]["rule_list_urls"]
                )
            item = discovered[full_name]
            item["seeded_source_urls"] = sorted(set(item.get("seeded_source_urls", [])) | set(seed_urls))
            item["rule_list_urls"] = sorted(set(item.get("rule_list_urls", [])) | set(seed_urls))
            seed_readme = fetch_readme(owner, name, item.get("default_branch") or "main")
            seed_claims = extract_readme_policy_claims(seed_readme, seed_urls)
            previous_claims = item.get("readme_policy_claims", {})
            item["readme_policy_claims"] = {
                url: sorted(set(previous_claims.get(url, [])) | set(seed_claims.get(url, [])))
                for url in set(previous_claims) | set(seed_claims)
            }
        merged = merge_candidates(existing, list(discovered.values()))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        message = "Source discovery degraded; previous discovery inventory retained. " + str(exc)
        print("WARNING: " + message, file=sys.stderr)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            Path(summary).write_text("## Source discovery warning\n\n" + message + "\n", encoding="utf-8")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(merged), encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"## Source discovery\n\nRepositories seen: **{len(discovered)}**. Candidates retained: **{merged['candidate_count']}**. No source was activated.\n")
    print(json.dumps({"repositories_seen": len(discovered), "candidates_retained": merged["candidate_count"], "activated": 0}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
