import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_domains import parse_source, parse_source_line_numbers

class SourceLineProvenanceTests(unittest.TestCase):
    def test_domain_only_preserves_line_and_suffix_scope(self):
        source={"id":"d","format":"domain-only","classification":"DIRECT","allow_leading_dot":True}
        data=b"# comment\nexample.com\n.sub.example.com\n"
        domains=parse_source(data,source)
        locations=parse_source_line_numbers(data,source)
        self.assertEqual(locations["example.com"],{"entry_type":"exact_candidate","line_number":2})
        self.assertEqual(locations["sub.example.com"],{"entry_type":"suffix_candidate","line_number":3})
        self.assertEqual(set(domains),set(locations))

    def test_adblock_records_original_source_line(self):
        source={"id":"r","format":"adblock-domain-rules","classification":"REJECT"}
        data=b"! title\n||ads.example^\n"
        self.assertEqual(parse_source_line_numbers(data,source)["ads.example"]["line_number"],2)

    def test_shadowrocket_and_quantumult_keep_source_scope_and_line(self):
        shadow={"id":"s","format":"shadowrocket-domain-rules","classification":"DIRECT"}
        raw=b"# header\nDOMAIN,api.example,DIRECT\nDOMAIN-SUFFIX,example.net,DIRECT\n"
        locations=parse_source_line_numbers(raw,shadow)
        self.assertEqual(locations["api.example"],{"entry_type":"exact_candidate","line_number":2})
        self.assertEqual(locations["example.net"],{"entry_type":"suffix_candidate","line_number":3})
        quantum={"id":"q","format":"quantumult-domain-rules","classification":"PROXY","policy_action_map":{"OUTSIDE":"PROXY"}}
        raw=b"# header\nHOST,api.example,OUTSIDE\nHOST-SUFFIX,example.net,OUTSIDE\n"
        locations=parse_source_line_numbers(raw,quantum)
        self.assertEqual(locations["api.example"],{"entry_type":"exact_candidate","line_number":2})
        self.assertEqual(locations["example.net"],{"entry_type":"suffix_candidate","line_number":3})

    def test_duplicate_domain_uses_first_line(self):
        source={"id":"d","format":"domain-only","classification":"DIRECT"}
        locations=parse_source_line_numbers(b"example.com\nexample.com\n",source)
        self.assertEqual(locations["example.com"]["line_number"],1)

if __name__ == "__main__":
    unittest.main()
