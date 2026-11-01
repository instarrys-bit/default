# Policy source overlap audit

This report compares normalized domain sets across discovered publisher feeds. It is informational only: overlap does not prove common ancestry, and low overlap does not prove independence.

- Feeds fetched: **10**
- Cross-policy conflict domains: **28**

| Policy | Publisher A | Publisher B | A domains | B domains | Shared | Smaller-set overlap | Jaccard |
|---|---|---|---:|---:|---:|---:|---:|
| DIRECT | ACL4SSR/ACL4SSR | Clash-FX/cn-apps-direct-domains | 605 | 120 | 73 | 60.8% | 11.2% |
| DIRECT | ACL4SSR/ACL4SSR | Jovanykoch/rules | 605 | 6751 | 439 | 72.6% | 6.3% |
| DIRECT | Clash-FX/cn-apps-direct-domains | Jovanykoch/rules | 120 | 6751 | 83 | 69.2% | 1.2% |
| PROXY | ACL4SSR/ACL4SSR | gatework/surge-rules | 6816 | 4451 | 3786 | 85.1% | 50.6% |
| PROXY | ACL4SSR/ACL4SSR | sve1r/Rules-For-Quantumult-X | 6816 | 574 | 371 | 64.6% | 5.3% |
| PROXY | gatework/surge-rules | sve1r/Rules-For-Quantumult-X | 4451 | 574 | 245 | 42.7% | 5.1% |

## Cross-policy contradictions

Detected domains appearing under more than one policy: **28**

- `2mdn.net`: DIRECT, PROXY
- `app-measurement.com`: DIRECT, PROXY
- `certs.apple.com`: DIRECT, REJECT
- `crl.apple.com`: DIRECT, REJECT
- `dytt8.net`: DIRECT, PROXY
- `globalsign.com`: DIRECT, PROXY
- `google-analytics.com`: DIRECT, PROXY
- `googleanalytics.com`: DIRECT, PROXY
- `googlesyndication.com`: DIRECT, PROXY
- `guzzoni-apple-com.v.aaplimg.com`: DIRECT, REJECT
- `helpshift.com`: DIRECT, PROXY
- `hotmail.com`: DIRECT, PROXY
- `ip138.com`: DIRECT, PROXY
- `manhuaren.com`: DIRECT, PROXY
- `mesu.apple.com`: DIRECT, REJECT
- `ocsp.apple.com`: DIRECT, REJECT
- `ocsp2.apple.com`: DIRECT, REJECT
- `oklink.com`: DIRECT, PROXY
- `playstation.com`: DIRECT, PROXY
- `playstation.net`: DIRECT, PROXY
- `playstationnetwork.com`: DIRECT, PROXY
- `recaptcha.net`: DIRECT, PROXY
- `simplecd.me`: DIRECT, PROXY
- `sony.com`: DIRECT, PROXY
- `sonyentertainmentnetwork.com`: DIRECT, PROXY
- `steamserver.net`: DIRECT, PROXY
- `ubnt.com`: DIRECT, PROXY
- `valid.apple.com`: DIRECT, REJECT

## Publication boundary

This stage does not add sources to the active registry, does not approve domains, and does not alter the three rule sets. Two genuinely independent, verified publishers and all existing deterministic gates remain required.
