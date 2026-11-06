#!/usr/bin/env python3
"""Validate the non-activating multi-source intelligence provider catalog."""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "sources/external_intelligence_catalog.json"
ALLOWED_HOSTS = {
    "github.com", "urlhaus.abuse.ch", "openphish.com", "crt.sh",
    "stat.ripe.net", "www.iana.org", "gitlab.com", "codeberg.org",
}
REQUIRED_CONTROLS = {
    "provider-specific HTTPS host allowlists and redirect validation",
    "bounded response sizes, timeouts, pagination, retries and per-provider budgets",
    "license and terms review before persistent ingestion",
    "publisher identity, source timestamp, retrieval timestamp and SHA-256 provenance",
    "upstream lineage and independence-group analysis",
    "separate domain, URL, DNS, certificate, ASN and IP data models",
    "no direct policy inference from geography, ASN, certificate, or threat-feed membership alone",
    "candidate-only quarantine until deterministic policy evidence and independent verification pass",
    "no writes to modules/uu.conf or user configuration; production output remains limited to authorized rule sets",
}

def validate_catalog(data: dict) -> list[str]:
    errors = []
    if data.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        return errors + ["providers must be a non-empty list"]
    seen = set()
    for item in providers:
        if not isinstance(item, dict):
            errors.append("provider entry must be an object")
            continue
        provider_id = item.get("id")
        if not isinstance(provider_id, str) or not provider_id or provider_id in seen:
            errors.append("provider IDs must be non-empty and unique")
            continue
        seen.add(provider_id)
        parsed = urlparse(str(item.get("endpoint", "")))
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
            errors.append(f"{provider_id}: endpoint is not on the HTTPS provider allowlist")
        if item.get("activation") not in {"never_from_catalog", "candidate_only", "evidence_only"}:
            errors.append(f"{provider_id}: invalid activation boundary")
        if item.get("integration_status") not in {"github_discovery_supported", "adapter_required", "query_adapter_required", "api_adapter_required", "discovery_adapter_required"}:
            errors.append(f"{provider_id}: invalid integration status")
        if not isinstance(item.get("data_types"), list) or not item["data_types"]:
            errors.append(f"{provider_id}: data_types must be non-empty")
    missing = REQUIRED_CONTROLS - set(data.get("required_future_controls", []))
    if missing:
        errors.append("missing future controls: " + ", ".join(sorted(missing)))
    if "modules/uu.conf" not in data.get("policy", "") and "modules/uu.conf" not in " ".join(data.get("required_future_controls", [])):
        errors.append("user config immutability boundary missing")
    return errors

def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    errors = validate_catalog(data)
    if errors:
        raise SystemExit("\n".join(errors))
    summary = [
        "## Multi-source intelligence catalog",
        "",
        f"Provider leads catalogued: **{len(data['providers'])}**",
        f"Adapters ready for production ingestion: **0** (catalog-only stage)",
        "Automatic activation from this catalog: **disabled**",
        "",
        "| Provider | Category | Data types | Integration status |",
        "|---|---|---|---|",
    ]
    for item in data["providers"]:
        summary.append(f"| {item['provider']} | {item['category']} | {', '.join(item['data_types'])} | {item['integration_status']} |")
    summary += ["", "**Safety boundary:** catalog validation performs no network requests, source downloads, rule classification, source admission, or repository writes."]
    summary_text = "\n".join(summary) + "\n"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as stream:
            stream.write(summary_text)
    print(json.dumps({"providers": len(data["providers"]), "production_adapters_ready": 0, "activated": 0}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
