# Domain source capture

Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
SHA-256: 48a27d8a7b52c0ce2abcfae93c18be9a49e7c7756e59f629684b036f6865a935
Current entries: 56516
New candidates detected: 0
Pending GPT review queue: 0
Initial baseline: established; existing entries were not queued

Only domain strings are captured. Upstream policy, scripts, modules, DNS, MITM and rewrite directives are never imported.
A compact Bloom filter tracks prior domains without storing a plain copy of the source list. Its false-positive probability is negligible; it has no false negatives.
Source removals never delete existing rules automatically. No config changes occur during capture.
