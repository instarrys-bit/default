# Domain candidate filter

Raw intake candidates at start: 0
Raw candidates processed this run: 0
Remaining intake backlog: 0
Candidates retained in GPT buffer: 67
Filtered and archived this run: 0

Checks: syntax, duplicate/review-ledger status, exact-vs-suffix scope, existing first-match DOMAIN/DOMAIN-SUFFIX, conditional rules, skip-proxy, DOMAIN-KEYWORD and URL-REGEX.
All raw intake candidates are evaluated in one run; there is no screening batch cap.
Filtered candidates are retained in reports/domain-filtered.json. All eligible candidates enter reports/pending-gpt-review.json. ss.conf is read-only.
