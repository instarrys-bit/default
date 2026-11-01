import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from deterministic_review import DOMAIN_RE, evidence_gate, inspect, validate_evidence
from domain_rule_engine import RuleIndex, DomainRule
from deterministic_review import CONFIG as REVIEW_CONFIG
from build_rulesets import CONFIG as RULESET_CONFIG
from collect_domains import bootstrap_source_domains, check_source_delta, parse_adblock, parse_domain_list, parse_source
from source_registry import validate_registry

class SourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.config={
            "sources":[
                {"id":"a","publisher":"publisher-a","independence_group":"group-a","url":"https://raw.githubusercontent.com/a/list","classification":"REJECT","format":"domain-only","role":"primary_candidate_source","lineage_status":"verified","lineage_evidence_url":"https://github.com/a/provenance","upstream_repositories":[],"weight":0.4},
                {"id":"b","publisher":"publisher-b","independence_group":"group-b","url":"https://raw.githubusercontent.com/b/list","classification":"REJECT","format":"domain-only","role":"independent_policy_corroboration","lineage_status":"verified","lineage_evidence_url":"https://github.com/b/provenance","upstream_repositories":[],"weight":0.4}
            ],
            "scoring":{
                "minimum_independent_sources":2,"minimum_confidence":0.8,
                "source_weights":{"a":0.4,"b":0.4},
                "required_sources_by_policy":{"DIRECT":[],"PROXY":[],"REJECT":["a","b"]}
            }
        }

    def test_current_registry_is_valid(self):
        self.assertEqual(set(validate_registry(self.config)),{"a","b"})

    def test_policy_without_primary_candidate_source_fails_closed(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][0]["role"]="independent_policy_corroboration"
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_policy_can_use_any_two_matching_sources_without_static_required_list(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"].append({"id":"c","publisher":"publisher-c","independence_group":"group-c","url":"https://raw.githubusercontent.com/c/list","classification":"DIRECT","format":"domain-only","role":"primary_candidate_source","lineage_status":"unverified","upstream_repositories":[],"weight":0.4})
        bad["scoring"]["source_weights"]["c"]=0.4
        self.assertIn("c",validate_registry(bad))

    def test_same_publisher_cannot_count_as_independent(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][1]["publisher"]="publisher-a"
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_required_source_must_match_policy_label(self):
        bad=json.loads(json.dumps(self.config))
        bad["scoring"]["required_sources_by_policy"]["DIRECT"]=["a","b"]
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_same_url_cannot_masquerade_as_two_independent_sources(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][1]["url"]=bad["sources"][0]["url"]
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_shared_declared_upstream_cannot_count_as_independent(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][0]["upstream_repositories"]=["shared/upstream"]
        bad["sources"][1]["upstream_repositories"]=["shared/upstream"]
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_unverified_source_lineage_is_retained_as_metadata(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][0]["lineage_status"]="unverified"
        self.assertIn("a",validate_registry(bad))

    def test_unknown_source_format_is_rejected(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][0]["format"]="unknown"
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_insecure_source_url_is_rejected(self):
        bad=json.loads(json.dumps(self.config))
        bad["sources"][0]["url"]="http://raw.githubusercontent.com/a/list"
        with self.assertRaises(ValueError):
            validate_registry(bad)


class DomainSyntaxTests(unittest.TestCase):
    def test_valid_fqdn_is_accepted(self):
        self.assertTrue(DOMAIN_RE.fullmatch('39d83s.com'))
        self.assertTrue(DOMAIN_RE.fullmatch('api.example.co.uk'))

    def test_single_label_and_invalid_hyphen_are_rejected(self):
        self.assertFalse(DOMAIN_RE.fullmatch('localhost'))
        self.assertFalse(DOMAIN_RE.fullmatch('-bad.example'))


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.weights={"sr-adblock-domain-lite":0.4,"hagezi-domains-pro":0.4}
        self.evidence=[
            {"source_id":"sr-adblock-domain-lite","publisher":"ithtelab/sr-adblock","independence_group":"sr-adblock-curated","lineage_status":"verified","currently_listed":True},
            {"source_id":"hagezi-domains-pro","publisher":"HaGeZi/dns-blocklists","independence_group":"hagezi-curated","lineage_status":"verified","currently_listed":True},
        ]

    def test_two_current_publishers_and_required_sources_pass(self):
        confidence,ids,publishers,groups,ok=evidence_gate(self.evidence,self.weights,2,0.8,{"sr-adblock-domain-lite","hagezi-domains-pro"})
        self.assertTrue(ok)
        self.assertEqual(confidence,0.8)
        self.assertEqual(len(publishers),2)
        self.assertEqual(len(groups),2)

    def test_unverified_lineage_can_qualify_when_two_publishers_agree(self):
        evidence=[dict(self.evidence[0],lineage_status="unverified"),dict(self.evidence[1],lineage_status="partial")]
        self.assertTrue(evidence_gate(evidence,self.weights,2,0.8,())[-1])

    def test_one_source_is_held(self):
        evidence=[self.evidence[0],dict(self.evidence[1],currently_listed=False)]
        self.assertFalse(evidence_gate(evidence,self.weights,2,0.8,{"sr-adblock-domain-lite","hagezi-domains-pro"})[-1])

    def test_same_publisher_or_group_cannot_fake_independence(self):
        evidence=[self.evidence[0],dict(self.evidence[1],publisher="ithtelab/sr-adblock",independence_group="sr-adblock-curated")]
        self.assertFalse(evidence_gate(evidence,self.weights,2,0.8,{"sr-adblock-domain-lite","hagezi-domains-pro"})[-1])

    def test_missing_required_source_is_held(self):
        self.assertFalse(evidence_gate(self.evidence,self.weights,2,0.8,{"unconfigured-source"})[-1])


class EvidenceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.source_map={
            "a":{"publisher":"publisher-a","independence_group":"group-a","url":"https://raw.githubusercontent.com/a/list","classification":"REJECT","lineage_status":"verified","upstream_repositories":[]},
            "b":{"publisher":"publisher-b","independence_group":"group-b","url":"https://raw.githubusercontent.com/b/list","classification":"REJECT","lineage_status":"verified","upstream_repositories":[]},
        }
        self.hashes={"a":"a"*64,"b":"b"*64}
        self.evidence=[
            {"source_id":"a","publisher":"publisher-a","independence_group":"group-a","url":"https://raw.githubusercontent.com/a/list","classification":"REJECT","lineage_status":"verified","upstream_repositories":[],"sha256":"a"*64,"currently_listed":True},
            {"source_id":"b","publisher":"publisher-b","independence_group":"group-b","url":"https://raw.githubusercontent.com/b/list","classification":"REJECT","lineage_status":"verified","upstream_repositories":[],"sha256":"b"*64,"currently_listed":True},
        ]

    def test_exact_registry_metadata_and_current_hashes_are_accepted(self):
        self.assertEqual(len(validate_evidence(self.evidence,self.source_map,self.hashes,"REJECT")),2)

    def test_forged_publisher_is_discarded(self):
        evidence=[dict(self.evidence[0],publisher="attacker"),self.evidence[1]]
        self.assertEqual(len(validate_evidence(evidence,self.source_map,self.hashes,"REJECT")),1)

    def test_stale_hash_is_discarded(self):
        evidence=[dict(self.evidence[0],sha256="0"*64),self.evidence[1]]
        self.assertEqual(len(validate_evidence(evidence,self.source_map,self.hashes,"REJECT")),1)

    def test_wrong_policy_or_url_is_discarded(self):
        evidence=[dict(self.evidence[0],classification="DIRECT"),dict(self.evidence[1],url="https://example.invalid/list")]
        self.assertEqual(validate_evidence(evidence,self.source_map,self.hashes,"REJECT"),[])


class UrlRegexScopeTests(unittest.TestCase):
    def base(self,rule):
        return "[General]\nskip-proxy = \n[Rule]\n"+rule+"\n[Host]\n"

    def test_generic_url_path_filter_does_not_conflict_with_every_domain(self):
        base=self.base(r"URL-REGEX,^http:\/\/[^\/]+\/multifetch\?dms=,REJECT")
        status,reason=inspect("example.com",RuleIndex([]),[],base,{},"DIRECT")
        self.assertIsNone(status)

    def test_host_specific_url_regex_only_conflicts_with_matching_host(self):
        base=self.base(r"URL-REGEX,^http:\/\/api\.bilibili\.com\/x\/vip\/ads\/,REJECT")
        status,reason=inspect("api.bilibili.com",RuleIndex([]),[],base,{},"DIRECT")
        self.assertEqual(status,"CONFLICT")
        status,reason=inspect("example.com",RuleIndex([]),[],base,{},"DIRECT")
        self.assertIsNone(status)



class RuleSetPrecedenceTests(unittest.TestCase):
    def test_rules_after_first_ruleset_do_not_affect_review(self):
        base = """[General]
skip-proxy =
[Rule]
RULE-SET,https://example.invalid/proxy.list,PROXY
DOMAIN,late.example.com,REJECT
DOMAIN-KEYWORD,late,REJECT
AND,((DOMAIN-SUFFIX,late.example.com),(GEOIP,CN)),REJECT
[Host]
"""
        rules = RuleIndex([DomainRule("DOMAIN", "late.example.com", "REJECT", 5, "DOMAIN,late.example.com,REJECT")])
        conditional = [(7, "AND,((DOMAIN-SUFFIX,late.example.com),(GEOIP,CN)),REJECT")]
        status, reason = inspect("late.example.com", rules, conditional, base, {}, "DIRECT")
        self.assertIsNone(status)

    def test_rules_before_first_ruleset_still_take_precedence(self):
        base = """[General]
skip-proxy =
[Rule]
DOMAIN-SUFFIX,example.com,REJECT
RULE-SET,https://example.invalid/proxy.list,PROXY
DOMAIN,late.example.com,DIRECT
[Host]
"""
        rules = RuleIndex([DomainRule("DOMAIN-SUFFIX", "example.com", "REJECT", 4, "DOMAIN-SUFFIX,example.com,REJECT")])
        status, reason = inspect("api.example.com", rules, [], base, {}, "DIRECT")
        self.assertEqual(status, "CONFLICT")


class SourceIntegrityTests(unittest.TestCase):
    def test_normalized_adblock_rule_is_parsed(self):
        self.assertEqual(parse_adblock(b'||ads.example^'), {'ads.example':'exact_candidate'})

    def test_source_dispatch_supports_registered_formats(self):
        self.assertEqual(parse_source(b'example.com', {'id':'x','format':'domain-only'}), {'example.com':'exact_candidate'})
        self.assertEqual(parse_source(b'||ads.example^', {'id':'y','format':'adblock-domain-rules'}), {'ads.example':'exact_candidate'})


    def test_shadowrocket_parser_extracts_only_exact_and_suffix_domains(self):
        from collect_domains import parse_shadowrocket_domain_rules
        data = b"""
        # comment
        DOMAIN,api.example.com
        DOMAIN-SUFFIX,example.org
        DOMAIN-KEYWORD,example
        IP-CIDR,192.0.2.0/24,no-resolve
        USER-AGENT,ExampleApp*
        """
        parsed = parse_shadowrocket_domain_rules(data, {"classification": "DIRECT"})
        self.assertEqual(parsed, {
            "api.example.com": "exact_candidate",
            "example.org": "suffix_candidate",
        })
        self.assertEqual(parse_shadowrocket_domain_rules(b"DOMAIN-SUFFIX,cn\nDOMAIN-SUFFIX,example.cn\n", {"classification":"DIRECT"}), {"example.cn":"suffix_candidate"})

    def test_quantumult_parser_accepts_trailing_rule_options(self):
        from collect_domains import parse_quantumult_domain_rules
        parsed=parse_quantumult_domain_rules(
            b"host-suffix,ptt.cc,OutSide,force-remote-dns\n",
            {"classification":"PROXY","policy_action_map":{"OUTSIDE":"PROXY"}},
        )
        self.assertEqual(parsed,{"ptt.cc":"suffix_candidate"})

    def test_shadowrocket_parser_rejects_explicit_policy_mismatch(self):
        from collect_domains import parse_shadowrocket_domain_rules
        with self.assertRaises(ValueError):
            parse_shadowrocket_domain_rules(
                b"DOMAIN,example.com,DIRECT",
                {"classification": "PROXY"},
            )

    def test_shadowrocket_parser_rejects_invalid_domain_rule(self):
        from collect_domains import parse_shadowrocket_domain_rules
        with self.assertRaises(ValueError):
            parse_shadowrocket_domain_rules(
                b"DOMAIN,not a domain",
                {"classification": "DIRECT"},
            )

    def test_unsupported_source_format_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_source(b'example.com', {'id':'x','format':'unknown'})

    def test_domain_list_regex_accepts_valid_fqdn(self):
        self.assertEqual(parse_domain_list(b'example.com')['example.com'], 'exact_candidate')

    def test_domain_list_deduplicates_repeated_entries(self):
        self.assertEqual(parse_domain_list(b'example.com\nexample.com\n'), {'example.com':'exact_candidate'})

    def test_domain_list_skips_single_label_artifacts(self):
        self.assertEqual(parse_domain_list(b'example.com\nalibaba\n'), {'example.com':'exact_candidate'})

    def test_primary_bootstrap_seeds_existing_snapshot_once(self):
        source={"role":"primary_candidate_source","bootstrap_enqueue":True}
        seen=set()
        domains={"one.example","two.example"}
        first,seeded=bootstrap_source_domains(source,"primary",seen,domains,set())
        self.assertTrue(seeded)
        self.assertEqual(first,domains)
        second,seeded_again=bootstrap_source_domains(source,"primary",seen,domains,set())
        self.assertFalse(seeded_again)
        self.assertEqual(second,set())

    def test_corroboration_source_does_not_seed_candidates(self):
        source={"role":"independent_policy_corroboration","bootstrap_enqueue":True}
        queued,seeded=bootstrap_source_domains(source,"corroborator",set(),{"one.example"},set())
        self.assertFalse(seeded)
        self.assertEqual(queued,set())

    def test_small_source_change_is_allowed(self):
        added, removed = check_source_delta(set('abcdefghij'), set('abcdefghiX'), 'test', ratio=0.10, minimum_absolute=2)
        self.assertEqual(added, {'X'})
        self.assertEqual(removed, {'j'})

    def test_large_source_change_fails_closed(self):
        previous={f'd{i}.example' for i in range(1000)}
        current={f'n{i}.example' for i in range(300)} | {f'd{i}.example' for i in range(700,1000)}
        with self.assertRaises(ValueError):
            check_source_delta(previous,current,'test',ratio=0.10,minimum_absolute=2)


class SourceScopeTests(unittest.TestCase):
    def test_leading_dot_suffix_scope_is_preserved(self):
        parsed=parse_domain_list(b".tracking.example\nexact.example\n",allow_leading_dot=True)
        self.assertEqual(parsed["tracking.example"],"suffix_candidate")
        self.assertEqual(parsed["exact.example"],"exact_candidate")

    def test_duplicate_apex_with_different_scope_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_domain_list(b".example.net\nexample.net\n",allow_leading_dot=True)


class LineageAuditTests(unittest.TestCase):
    def test_extracts_and_normalizes_public_upstream_repository_links(self):
        from audit_source_lineage import extract_upstreams
        text = "https://github.com/Example/Repo https://codeberg.org/Owner/Filters https://gitlab.com/team/list"
        self.assertEqual(extract_upstreams(text), {"example/repo", "codeberg:owner/filters", "gitlab:team/list"})


    def test_peter_lowe_aliases_collapse_to_one_upstream(self):
        from audit_source_lineage import normalize_upstream
        self.assertEqual(normalize_upstream("external:peter-lowe"), "peter-lowe")
        self.assertEqual(normalize_upstream("peter-lowe:pgl.yoyo.org"), "peter-lowe")
        self.assertEqual(normalize_upstream("PGL.YOYO.ORG"), "peter-lowe")
        self.assertEqual(normalize_upstream("Example/Repo"), "example/repo")

    def test_lineage_audit_detects_shared_upstreams_without_verifying(self):
        from audit_source_lineage import audit_registry
        config = {"sources": [
            {"id":"a","publisher":"publisher-a","lineage_status":"partial","lineage_evidence_url":"https://github.com/a/provenance/blob/main/sources.md","upstream_repositories":["shared/upstream"]},
            {"id":"b","publisher":"publisher-b","lineage_status":"partial","lineage_evidence_url":"https://github.com/b/provenance/blob/main/sources.md","upstream_repositories":["shared/upstream"]}
        ]}
        def fake_fetch(url):
            return b"https://github.com/shared/upstream"
        report = audit_registry(config, fake_fetch)
        self.assertEqual(len(report["shared_upstream_pairs"]), 1)
        self.assertEqual(report["lineage_verified_count"], 0)
        self.assertEqual(report["audited_source_count"], 2)


class SourceDiscoveryTests(unittest.TestCase):
    def test_extracts_only_repo_owned_list_urls(self):
        from discover_sources import extract_list_urls
        text = """
        https://raw.githubusercontent.com/acme/rules/main/direct.list
        https://github.com/acme/rules/blob/main/proxy.txt
        https://raw.githubusercontent.com/other/repo/main/not-owned.list
        https://example.com/foreign.list
        """
        self.assertEqual(
            set(extract_list_urls(text, "acme", "rules", "main")),
            {
                "https://raw.githubusercontent.com/acme/rules/main/direct.list",
                "https://raw.githubusercontent.com/acme/rules/main/proxy.txt",
            },
        )

    def test_discovery_merge_preserves_first_seen_and_unions_links(self):
        from discover_sources import merge_candidates
        old = {"candidates": [{
            "repository": "acme/rules", "discovered_at": "2026-01-01",
            "search_queries": ["old query"], "rule_list_urls": ["https://raw.githubusercontent.com/acme/rules/main/a.list"]
        }]}
        new = [{
            "repository": "acme/rules", "discovered_at": "2026-11-01",
            "search_queries": ["new query"], "rule_list_urls": ["https://raw.githubusercontent.com/acme/rules/main/b.list"]
        }]
        result = merge_candidates(old, new)
        item = result["candidates"][0]
        self.assertEqual(item["discovered_at"], "2026-01-01")
        self.assertEqual(set(item["search_queries"]), {"old query", "new query"})
        self.assertEqual(len(item["rule_list_urls"]), 2)
        self.assertIn("never adds or enables", result["activation_policy"])


    def test_sensitive_adult_list_urls_are_excluded(self):
        from discover_sources import extract_list_urls
        text = "https://raw.githubusercontent.com/acme/rules/main/porno.txt https://raw.githubusercontent.com/acme/rules/main/ads.list"
        self.assertEqual(
            extract_list_urls(text, "acme", "rules", "main"),
            ["https://raw.githubusercontent.com/acme/rules/main/ads.list"],
        )

    def test_irrelevant_search_results_are_not_retained_without_rule_files(self):
        from discover_sources import merge_candidates
        result = merge_candidates({"candidates": []}, [{
            "repository": "someone/online-bible",
            "description": "Chinese Bible sermons",
            "discovered_at": "2026-11-01",
            "rule_list_urls": [],
            "search_queries": ["China domain list"],
        }])
        self.assertEqual(result["candidate_count"], 0)


class SourceAssessmentTests(unittest.TestCase):
    def test_explicit_shadowrocket_policy_is_detected_and_non_domains_are_ignored(self):
        from assess_sources import assess_payload
        payload = b"""
        DOMAIN,api.example.com,DIRECT
        DOMAIN-SUFFIX,example.org,DIRECT
        DOMAIN-KEYWORD,example
        IP-CIDR,192.0.2.0/24,no-resolve
        """
        result = assess_payload(payload, "https://raw.githubusercontent.com/a/b/main/x.list", [])
        self.assertEqual(result["policy_candidate"], "DIRECT")
        self.assertEqual(result["policy_evidence"], "explicit_third_field")
        self.assertEqual(result["domain_keyword_rules_ignored"], 1)
        self.assertEqual(result["ip_asn_rules_ignored"], 1)
        self.assertEqual(result["exact_domain_count"], 1)
        self.assertEqual(result["suffix_domain_count"], 1)

    def test_partial_or_mixed_domain_actions_do_not_claim_a_policy(self):
        from assess_sources import assess_payload
        partial = assess_payload(
            b"DOMAIN,a.example,DIRECT\nDOMAIN,b.example\n",
            "https://raw.githubusercontent.com/a/b/main/x.list", []
        )
        mixed = assess_payload(
            b"DOMAIN,a.example,DIRECT\nDOMAIN,b.example,PROXY\n",
            "https://raw.githubusercontent.com/a/b/main/x.list", []
        )
        self.assertIsNone(partial["policy_candidate"])
        self.assertIsNone(mixed["policy_candidate"])

    def test_readme_policy_claim_requires_exact_rule_set_reference(self):
        from assess_sources import readme_policy_claim
        url = "https://raw.githubusercontent.com/acme/rules/main/direct.list"
        readme = "RULE-SET," + url + ",DIRECT"
        self.assertEqual(readme_policy_claim(readme, url), ["DIRECT"])


    def test_discovery_extracts_exact_rule_set_policy_claims(self):
        from discover_sources import extract_readme_policy_claims
        url = "https://raw.githubusercontent.com/acme/rules/main/domestic.list"
        readme = "RULE-SET," + url + ",DIRECT"
        self.assertEqual(extract_readme_policy_claims(readme, [url]), {url: ["DIRECT"]})


    def test_quantumult_parser_maps_outside_to_proxy_and_ignores_non_domains(self):
        from collect_domains import parse_quantumult_domain_rules
        payload = b"""
        host-suffix,example.cn,direct
        host,api.example.cn,direct
        host-suffix,foreign.example,OutSide
        user-agent,ExampleApp*,direct
        host-keyword,example,direct
        geoip,CN,direct
        """
        direct = parse_quantumult_domain_rules(
            payload.replace(b"host-suffix,foreign.example,OutSide\n", b""),
            {"classification": "DIRECT"}
        )
        proxy = parse_quantumult_domain_rules(
            b"host-suffix,foreign.example,OutSide",
            {"classification": "PROXY", "policy_action_map": {"OUTSIDE": "PROXY"}}
        )
        self.assertEqual(direct, {"example.cn": "suffix_candidate", "api.example.cn": "exact_candidate"})
        self.assertEqual(proxy, {"foreign.example": "suffix_candidate"})

    def test_quantumult_parser_rejects_wrong_policy(self):
        from collect_domains import parse_quantumult_domain_rules
        with self.assertRaises(ValueError):
            parse_quantumult_domain_rules(
                b"host-suffix,example.com,OutSide",
                {"classification": "DIRECT", "policy_action_map": {"OUTSIDE": "PROXY"}}
            )


    def test_quantumult_outside_is_assessed_as_proxy(self):
        from assess_sources import assess_payload
        payload = b"\n".join(
            [f"host-suffix,d{i}.example,OutSide".encode() for i in range(25)]
        )
        result = assess_payload(payload, "https://raw.githubusercontent.com/a/b/main/global.list", [])
        self.assertEqual(result["parser_candidate"], "quantumult-domain-rules")
        self.assertEqual(result["policy_candidate"], "PROXY")
        self.assertEqual(result["policy_evidence"], "explicit_third_field")


    def test_seeded_source_urls_are_preserved_in_discovery_merge(self):
        from discover_sources import merge_candidates
        result = merge_candidates({"candidates": []}, [{
            "repository": "acme/rules", "description": "Shadowrocket rules",
            "discovered_at": "2026-11-01",
            "rule_list_urls": ["https://raw.githubusercontent.com/acme/rules/main/a.list"],
            "seeded_source_urls": ["https://raw.githubusercontent.com/acme/rules/main/a.list"],
            "search_queries": ["curated_seed"],
        }])
        item = result["candidates"][0]
        self.assertEqual(item["seeded_source_urls"], item["rule_list_urls"])


    def test_candidate_source_readme_references_are_compared_but_not_verified(self):
        from audit_source_lineage import audit_registry
        config = {"sources": []}
        candidates = [
            {"repository":"alpha/rules","default_branch":"main","rule_list_urls":["https://raw.githubusercontent.com/alpha/rules/main/a.list"]},
            {"repository":"beta/rules","default_branch":"main","rule_list_urls":["https://raw.githubusercontent.com/beta/rules/main/b.list"]},
        ]
        def fake_fetch(url):
            return b"https://github.com/shared/upstream"
        report = audit_registry(config, fake_fetch, candidates)
        self.assertEqual(report["candidate_readme_audited_count"], 2)
        self.assertEqual(len(report["candidate_shared_reference_pairs"]), 1)
        self.assertEqual(report["candidate_sources"][0]["lineage_status"], "unverified")


    def test_shadowrocket_parser_deduplicates_same_scope_but_rejects_scope_conflict(self):
        from collect_domains import parse_shadowrocket_domain_rules
        parsed = parse_shadowrocket_domain_rules(
            b"DOMAIN-SUFFIX,example.com\nDOMAIN-SUFFIX,example.com\n",
            {"classification": "DIRECT"}
        )
        self.assertEqual(parsed, {"example.com": "suffix_candidate"})
        with self.assertRaises(ValueError):
            parse_shadowrocket_domain_rules(
                b"DOMAIN,example.com\nDOMAIN-SUFFIX,example.com\n",
                {"classification": "DIRECT"}
            )

    def test_quantumult_parser_deduplicates_same_scope(self):
        from collect_domains import parse_quantumult_domain_rules
        parsed = parse_quantumult_domain_rules(
            b"host-suffix,example.com,direct\nhost-suffix,example.com,direct\n",
            {"classification": "DIRECT"}
        )
        self.assertEqual(parsed, {"example.com": "suffix_candidate"})


class SourceCandidateMatrixTests(unittest.TestCase):
    def test_multiple_files_from_one_repository_count_as_one_publisher(self):
        from build_source_candidates import build_matrix
        assessments = {"assessments": [
            {"repository":"one/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"README_RULE-SET_reference","exact_domain_count":10,"suffix_domain_count":20,"adblock_domain_count":0,"domain_only_count":0,"url":"https://raw.githubusercontent.com/one/rules/main/a.list","archived":False},
            {"repository":"one/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"README_RULE-SET_reference","exact_domain_count":5,"suffix_domain_count":10,"adblock_domain_count":0,"domain_only_count":0,"url":"https://raw.githubusercontent.com/one/rules/main/b.list","archived":False},
            {"repository":"two/rules","policy_candidate":"DIRECT","parser_candidate":"quantumult-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":2,"suffix_domain_count":3,"adblock_domain_count":0,"domain_only_count":0,"url":"https://raw.githubusercontent.com/two/rules/main/c.list","archived":False},
        ]}
        lineage = {"candidate_sources": [
            {"repository":"one/rules","lineage_status":"unverified","status":"audited_reference_inventory","reference_count":0},
            {"repository":"two/rules","lineage_status":"unverified","status":"audited_reference_inventory","reference_count":0},
        ]}
        result = build_matrix(assessments, lineage)
        self.assertEqual(result["policy_summary"]["DIRECT"]["candidate_publishers"], 2)
        self.assertEqual(result["policy_summary"]["DIRECT"]["candidate_files"], 3)
        self.assertEqual(result["activation_count"], 0)

    def test_possible_shared_readme_references_are_recorded_as_blockers(self):
        from build_source_candidates import build_matrix
        assessments = {"assessments": [
            {"repository":"one/rules","policy_candidate":"PROXY","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":1,"suffix_domain_count":2,"adblock_domain_count":0,"domain_only_count":0,"url":"https://raw.githubusercontent.com/one/rules/main/a.list","archived":False},
        ]}
        lineage = {"candidate_sources":[{"repository":"one/rules","lineage_status":"unverified","status":"audited_reference_inventory","reference_count":1}],
                   "candidate_shared_reference_pairs":[{"repositories":["one/rules","two/rules"],"shared_readme_references":["common/upstream"]}]}
        result = build_matrix(assessments, lineage)
        item = result["candidates"][0]
        self.assertIn("possible_shared_readme_references_require_review", item["activation_blockers"])
        self.assertFalse(item["activation_eligible"])


    def test_readme_policy_claim_detects_documented_source_table_semantics(self):
        from discover_sources import extract_readme_policy_claims
        direct = "https://raw.githubusercontent.com/acme/rules/main/ChinaDomain.list"
        proxy = "https://raw.githubusercontent.com/acme/rules/main/ProxyLite.list"
        readme = "| ChinaDomain.list | 规则碎片-直连 |\n| ProxyLite.list | 规则碎片-代理 |"
        self.assertEqual(
            extract_readme_policy_claims(readme, [direct, proxy]),
            {direct: ["DIRECT"], proxy: ["PROXY"]},
        )


    def test_matching_readme_policy_reference_strengthens_header_claim(self):
        from assess_sources import assess_payload
        result = assess_payload(
            "# 代理列表\nDOMAIN-SUFFIX,example.com".encode("utf-8"),
            "https://raw.githubusercontent.com/a/b/main/proxy.list",
            ["PROXY"],
        )
        self.assertEqual(result["policy_candidate"], "PROXY")
        self.assertEqual(result["policy_evidence"], "README_policy_reference")

    def test_conflicting_readme_and_file_header_policy_is_ambiguous(self):
        from assess_sources import assess_payload
        result = assess_payload(
            "# 代理列表\nDOMAIN-SUFFIX,example.com".encode("utf-8"),
            "https://raw.githubusercontent.com/a/b/main/proxy.list",
            ["DIRECT"],
        )
        self.assertIsNone(result["policy_candidate"])
        self.assertEqual(result["policy_evidence"], "ambiguous")


    def test_near_duplicate_domain_sets_do_not_count_as_two_independent_groups(self):
        from build_source_candidates import build_matrix
        shared = ["a"*32, "b"*32, "c"*32]
        assessments = {"assessments": [
            {"repository":"one/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":3,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":shared,"url":"https://raw.githubusercontent.com/one/rules/main/a.list","archived":False},
            {"repository":"two/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":3,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":shared,"url":"https://raw.githubusercontent.com/two/rules/main/a.list","archived":False},
        ]}
        lineage = {"candidate_sources":[
            {"repository":"one/rules","lineage_status":"verified","status":"audited_reference_inventory","reference_count":0},
            {"repository":"two/rules","lineage_status":"verified","status":"audited_reference_inventory","reference_count":0},
        ]}
        result = build_matrix(assessments, lineage)
        self.assertEqual(result["same_policy_domain_overlap"][0]["relation"], "near_duplicate")
        self.assertEqual(result["policy_summary"]["DIRECT"]["independent_verified_groups"], 1)
        self.assertFalse(result["policy_summary"]["DIRECT"]["activation_ready"])

    def test_cross_policy_domain_overlap_is_reported_without_raw_domains(self):
        from build_source_candidates import build_matrix
        assessments = {"assessments": [
            {"repository":"one/direct","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":1,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":["a"*32],"url":"https://raw.githubusercontent.com/one/direct/main/a.list","archived":False},
            {"repository":"two/proxy","policy_candidate":"PROXY","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":1,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":["a"*32],"url":"https://raw.githubusercontent.com/two/proxy/main/a.list","archived":False},
        ]}
        lineage = {"candidate_sources":[]}
        result = build_matrix(assessments, lineage)
        self.assertEqual(result["cross_policy_conflicts"][0]["shared_domain_count"], 1)
        self.assertNotIn("domain_fingerprints", result["candidates"][0])


class SourceDriftTests(unittest.TestCase):
    def test_unchanged_source_has_zero_domain_drift(self):
        from assess_sources import compare_drift
        item = {"sha256":"same","domain_fingerprints":["a","b"],"policy_candidate":"DIRECT","policy_evidence":"explicit_third_field"}
        result = compare_drift(item, item)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["added_domain_count"], 0)

    def test_domain_set_changes_are_counted_without_emitting_domains(self):
        from assess_sources import compare_drift
        old = {"sha256":"old","domain_fingerprints":["a","b"],"policy_candidate":"DIRECT","policy_evidence":"explicit_third_field"}
        new = {"sha256":"new","domain_fingerprints":["b","c","d"],"policy_candidate":"DIRECT","policy_evidence":"explicit_third_field"}
        result = compare_drift(new, old)
        self.assertEqual(result["status"], "domain_set_changed")
        self.assertEqual(result["added_domain_count"], 2)
        self.assertEqual(result["removed_domain_count"], 1)
        self.assertNotIn("added_domains", result)

    def test_policy_change_is_reported_even_when_source_bytes_are_unchanged(self):
        from assess_sources import compare_drift
        old = {"sha256":"same","domain_fingerprints":["a"],"policy_candidate":"DIRECT","policy_evidence":"README_policy_reference"}
        new = {"sha256":"same","domain_fingerprints":["a"],"policy_candidate":"PROXY","policy_evidence":"README_policy_reference"}
        result = compare_drift(new, old)
        self.assertEqual(result["status"], "policy_metadata_changed")
        self.assertTrue(result["policy_changed"])

class DiscoveryPolicyClaimTests(unittest.TestCase):
    def test_explicit_readme_semantics_are_detected_for_seeded_feeds(self):
        from discover_sources import extract_readme_policy_claims
        direct = "https://raw.githubusercontent.com/example/rules/rel/loc-cn.list"
        proxy = "https://raw.githubusercontent.com/example/rules/rel/gfw.list"
        reject = "https://raw.githubusercontent.com/example/rules/rel/reject.list"
        readme = """
* `loc-cn`: Rules for direct connections in mainland China
* `gfw`: Proxy rules from a maintained source
* `reject`: Advertising and blocked-domain rules
"""
        self.assertEqual(
            extract_readme_policy_claims(readme, [direct, proxy, reject]),
            {direct: ["DIRECT"], proxy: ["PROXY"], reject: ["REJECT"]},
        )

    def test_conflicting_readme_descriptions_remain_ambiguous(self):
        from discover_sources import extract_readme_policy_claims
        url = "https://raw.githubusercontent.com/example/rules/main/domains.list"
        readme = "domains.list: direct and proxy domain list"
        self.assertEqual(extract_readme_policy_claims(readme, [url])[url], ["DIRECT", "PROXY"])


class HighOverlapIndependenceTests(unittest.TestCase):
    def test_high_overlap_publishers_are_not_counted_as_independent_groups(self):
        from build_source_candidates import build_matrix
        shared = [str(i).zfill(32) for i in range(8)]
        left = shared + ["a"*32, "b"*32]
        right = shared + ["c"*32, "d"*32]
        assessments = {"assessments": [
            {"repository":"one/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":10,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":left,"url":"https://raw.githubusercontent.com/one/rules/main/a.list","archived":False},
            {"repository":"two/rules","policy_candidate":"DIRECT","parser_candidate":"shadowrocket-domain-rules","policy_evidence":"explicit_third_field","exact_domain_count":10,"suffix_domain_count":0,"adblock_domain_count":0,"domain_only_count":0,"domain_fingerprints":right,"url":"https://raw.githubusercontent.com/two/rules/main/a.list","archived":False},
        ]}
        lineage = {"candidate_sources":[
            {"repository":"one/rules","lineage_status":"verified","status":"audited_reference_inventory","reference_count":0},
            {"repository":"two/rules","lineage_status":"verified","status":"audited_reference_inventory","reference_count":0},
        ]}
        result = build_matrix(assessments, lineage)
        self.assertEqual(result["same_policy_domain_overlap"][0]["relation"], "high_overlap")
        self.assertEqual(result["policy_summary"]["DIRECT"]["independent_verified_groups"], 1)
        self.assertFalse(result["policy_summary"]["DIRECT"]["activation_ready"])


if __name__=="__main__":
    unittest.main(verbosity=2)


class UserConfigBaselineTests(unittest.TestCase):
    def test_domain_review_and_rule_builder_use_user_managed_config(self):
        expected = ROOT / "shadowrocket" / "ss.conf"
        self.assertEqual(REVIEW_CONFIG, expected)
        self.assertEqual(RULESET_CONFIG, expected)
