# Domain candidate filter

Raw intake candidates at start: 56516
Raw candidates processed this run: 1000
Remaining intake backlog: 55516
Candidates retained in GPT buffer: 1
Filtered and archived this run: 999

Checks: syntax, duplicate/review-ledger status, exact-vs-suffix scope, existing first-match DOMAIN/DOMAIN-SUFFIX, conditional rules, skip-proxy, DOMAIN-KEYWORD and URL-REGEX.
Processing limits: at most 1000 raw candidates per run and 100 candidates in the GPT buffer.
Filtered candidates are retained in reports/domain-filtered.json. Unprocessed candidates remain in reports/domain-intake.json for later runs. ss.conf is read-only.
