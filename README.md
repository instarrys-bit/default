# Shadowrocket 项目

本仓库独立维护 Shadowrocket DIRECT、PROXY、REJECT 三类规则集及其托管自动化。主配置仅作为用户独立维护对象，不由规则集自动化修改。

## 主配置

- 主配置文件：[`shadowrocket/ss.conf`](shadowrocket/ss.conf)
- 订阅地址：`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

主配置是独立维护对象。迁移脚本和模块时，不自动启用它们，也不自动改动主配置中的 DNS、规则或 MITM 设置。

## 项目目录

- `.github/workflows/`：GitHub Actions 工作流
- `shadowrocket/ss.conf`：主配置
- `rulesets/`：DIRECT、PROXY、REJECT 规则集及清单
- `sources/`：域名来源、确定性审核账本、策略与主配置保护元数据
- `scripts/`：域名采集、确定性证据审核、冲突检测、规则集构建和质量验证
- `data/`、`reports/`、`dist/`：采集数据、审计报告和构建产物
- `modules/AdBlock.sgmodule`：用户维护的广告处理模块
- `modules/adblock/`：模块运行脚本及第三方衍生代码的许可证与来源声明

## 可选模块的使用边界

迁移到仓库不代表已启用或已验证其设备端效果：

- `modules/AdBlock.sgmodule`：用户维护的定向广告处理模块。
- `modules/adblock/scripts/Social_Adblock.js`：社交与搜索响应处理脚本。
- `modules/adblock/scripts/youtube_initplayback_observer.js`：仅在本地记录 YouTube initplayback 主机名，不保存完整 URL，也不发起网络请求。
- `modules/adblock/scripts/youtube_protobuf_response_filter.js`：项目维护的 YouTube Protobuf 响应处理脚本（沿用原有文件路径）；属于基于 Maasea 上游代码的派生版本，必要来源说明与 Apache 2.0 许可证继续保留。
- 旧的独立 `youtube-ads.sgmodule` 已从当前目录结构移除，不再作为本项目发布模块。

这些模块不会因文件迁移而自动进入 `ss.conf`。在确认兼容性、隐私边界和设备端效果之前，不应直接启用。

## 许可证与来源

`modules/adblock/LICENSE-APACHE-2.0-Maasea` 保留 Maasea 上游 Apache 2.0 许可证。使用、修改或再分发相关上游代码时，应阅读并遵守该许可证及各文件原有版权声明。


## GitHub-only 域名观察入口

本项目不依赖 Cloudflare Worker 或 KV。需要补充设备观察到的域名时，可在 GitHub Actions 中手动运行 `GitHub-only observed-domain intake`，粘贴纯 hostname（每次最多 500 个），工作流会校验格式、合并到 `sources/request_domain_observations.json`，再触发确定性规则审核。该入口不接收完整 URL、查询参数、请求头、请求体或客户端标识。由于 GitHub Actions 不是常驻接收服务器，手机端不会自动实时推送；设备日志需要先提取 hostname，再通过 GitHub 工作流导入。

## 确定性审核与自动发布

唯一发布工作流为 `.github/workflows/auto_sync.yml`：支持手动运行，并按每天北京时间 04:00 自动运行；独立 watchdog 每天检查最近一次成功记录，超过 25 小时未成功且没有运行中的任务时自动补发一次审计。全程纯确定性托管自动化，不包含 AI、LLM、模型 API、API Key 或人工逐条审核依赖。流程为来源采集、域名规范化、跨来源证据核验、重复/冲突/保护检查、三类规则集构建、静态验证、报告与版本提交。安全边界采用独立作业：审计作业仅有 `contents: read` 且不保留 checkout 凭据；仅发布作业具有 `contents: write`，它不执行仓库 Python 脚本，只接收短期保留的白名单产物并再次核验基准提交后发布。失败通知作业单独拥有 `issues: write`；来源采集对 HTTP 408/425/429/5xx 与网络超时执行最多 3 次有限退避重试，永久 4xx、格式异常和安全门槛失败不重试；后续完整审计与发布成功后，自动关闭对应故障 Issue。

当前登记了三类策略来源：DIRECT 使用 ACL4SSR ChinaDomain 与 Clash-FX cn-apps-direct-domains；PROXY 使用 ACL4SSR ProxyLite 与 sve1r Global；REJECT 使用 sr-adblock-domain-lite 与 HaGeZi Pro。每个域名必须获得至少两个不同发布者、不同来源组的当前证据，策略一致并通过本地检查，才可进入对应规则集。来源血缘状态会完整记录，但 `partial` 或 `unverified` 不再一票否决域名；来源重叠是相关性提示，不等同于具体域名共享上游。

单一来源、策略证据不足、跨策略冲突、条件规则交叠或关键服务风险命中的域名不会直接发布；单源候选进入观察状态，跨策略冲突隔离。脚本不会根据域名名称、TLD、IP 地理位置或 DNS 结果猜测策略；后缀级候选保留来源声明的范围；只有至少两个独立发布者明确提供相同后缀范围并通过范围冲突、条件规则、保护域名和配置优先级检查，才会生成 `DOMAIN-SUFFIX`。精确域名和后缀域名均可发布，不增加 DIRECT、PROXY、REJECT 之外的分流策略。

证据不足、来源冲突/移除、已有规则覆盖、现有规则策略冲突、条件规则交叠或关键功能保护命中，均不会发布。历史 Gemini/GPT 审核流程已退役，其旧审核账本、待审队列和发布报告已从当前分支清理（Git 历史仍可追溯）；当前工作流、脚本和规则集构建不调用任何 AI/LLM 或模型 API。唯一审核账本为 `sources/domain_reviews.json`，规则判断完全由可测试的确定性证据与安全门槛完成。

审核账本：`sources/domain_reviews.json`。发布统计：`rulesets/manifest.json`。`shadowrocket/ss.conf` 是唯一权威主配置；自动化只读取它并核对登记的 Git blob SHA，不会修改或提交它。

每次构建还会在 `rulesets/manifest.json` 的 `rule_lifecycle` 中记录 DIRECT、PROXY、REJECT 三类规则集各自的前后数量、增加/移除数量、前后 SHA-256 和最多 10 条变化样例。该记录只用于审计动态变化，不改变证据门槛；输出目录严格只允许 `direct.list`、`proxy.list`、`reject.list` 三个策略文件。

## 验证边界

静态验证可以检查来源一致性、格式、规则覆盖和构建结果，但不能代替 Shadowrocket 设备端测试。任何新规则集都应先单独订阅、观察关键 App 和系统服务，再考虑长期使用。

## DIRECT / PROXY source research

The current source-provenance assessment is recorded in [`reports/direct-proxy-source-research.md`](reports/direct-proxy-source-research.md). Candidate lists are not activated merely because they are labelled China, Global, or Proxy; documented upstream overlap and policy semantics are checked first. The automated source-discovery and assessment inventories are stored in `sources/discovered_sources.json`, `sources/source_assessments.json`, and `reports/source-assessment.md`.

## Deterministic multi-source collection

The collector is registry-driven: it downloads every enabled source, dispatches only to explicitly supported parsers, verifies each source independently, and stores a separate snapshot under `data/source_snapshots/<source-id>.txt`. Only sources marked `primary_candidate_source` enqueue newly observed domains; other registered sources provide corroborating evidence. A domain present under more than one routing policy is held as `POLICY_CONFLICT`, never resolved by source order.

Supported source formats are `domain-only` (including an explicitly enabled leading-dot suffix mode), `adblock-domain-rules`, `shadowrocket-domain-rules`, and `quantumult-domain-rules`. The parsers extract only supported domain entries; they never convert `DOMAIN-KEYWORD`, `USER-AGENT`, IP/CIDR, ASN, process or other rules into domains. Broad single-label suffixes are excluded and repeated identical entries are deduplicated. If a source embeds an explicit action, it must match the registry classification or an explicit action map. Every enabled source declares policy, publisher, independence group, parser format, role, HTTPS Raw URL, scoring weight and policy-evidence type. Publication is evaluated per domain; optional required-source lists may add constraints but do not require every enabled source to be present.

New sources initialize a baseline without bulk-enqueuing their entire contents by default. A primary source explicitly marked `bootstrap_enqueue` may seed its initial domain set once; subsequent runs enqueue only additions. Corroboration sources never enqueue candidates by themselves. Source snapshots are committed by the scheduled workflow so change detection survives runner replacement.


### Automated source ancestry audit

`scripts/audit_source_lineage.py` runs in every scheduled audit. It fetches each registered public provenance document, extracts referenced GitHub/Codeberg/GitLab repositories, compares discovered references with the registry, and reports newly discovered or stale declarations plus shared upstreams in `reports/source-lineage-audit.json`. It does not modify source policy or automatically declare lineage verified: repository-level link discovery is not proof of per-domain provenance. Failures to retrieve or parse a registered provenance document stop the audit rather than silently treating missing evidence as independence.

### Source ancestry and publication gate

Publisher names and separate repository URLs are not sufficient proof of independent evidence. Every registered source declares `lineage_status` and `upstream_repositories`. Sources with `verified`, `partial` or `unverified` lineage can contribute to domain-level corroboration when their current identity, hash and policy evidence match the registry. Lineage is disclosed in the ledger and reports; it is not a blanket publication veto. Distinct publisher identity and current per-domain agreement remain required. Declared shared upstream repositories prevent sources from meeting the independence minimum. See the provenance report for current source status. The scheduled writer uses a normal fail-closed rebase; it never resolves output conflicts by preferring the automation branch.


## Automated source discovery

`scripts/discover_sources.py` searches GitHub on every scheduled run for repositories related to Shadowrocket rules, China domain lists, proxy/direct domain lists, geosite and adblock domains. It inspects public README files for repository-owned `.list`, `.txt` and `.conf` URLs, then stores candidate repositories and source links in `sources/discovered_sources.json` and `reports/source-discovery.md`.

Discovery is intentionally non-activating. Search terms and repository names are not policy evidence. A candidate cannot enter `sources/domain_sources.json` until policy semantics, exact parser compatibility, publisher identity, lineage/overlap and update-drift checks pass. A GitHub API outage retains the previous inventory and does not interrupt the independent deterministic audit.

The automation guards the single authoritative user-managed config `shadowrocket/ss.conf` by Git blob SHA. An owner-approved change is registered in `sources/policy.json`; any other mismatch fails the integrity gate. The workflow never stages or commits `shadowrocket/ss.conf`.


## Automated source assessment

`scripts/assess_sources.py` runs after repository discovery. It fetches only rule-list URLs hosted by the discovered repository, checks supported domain syntax, counts exact and suffix domain rules, and records non-domain rules such as DOMAIN-KEYWORD, IP/CIDR and ASN as ignored. It recognizes a routing policy only when all domain rules carry one consistent explicit action or the README contains an exact RULE-SET URL/action reference. Mixed or incomplete policy evidence remains unclassified.

Assessment results are stored in `sources/source_assessments.json` and `reports/source-assessment.md`. This stage never activates sources or modifies the trusted source registry.


The source-discovery stage also rechecks curated candidate feeds from Hackl0us, sve1r, ACL4SSR, blackmatrix7, Loyalsoldier, Jovanykoch, gatework and Clash-FX. These seed URLs are discovery leads, not approved or active routing sources. Their policy meaning, parser compatibility and ancestry are reassessed on every scheduled run. README policy claims are accepted only when the specific list is described with an explicit routing meaning; conflicting descriptions remain ambiguous.


## Automated source candidate matrix

After lineage auditing, `scripts/build_source_candidates.py` joins parser assessments with policy evidence and possible shared README references. Multiple files from one repository count as one publisher. It reports DIRECT, PROXY and REJECT candidate publisher counts, policy-evidence-eligible publisher counts and candidate eligibility blockers in `sources/source_candidates.json` and `reports/source-candidate-matrix.md`.

The candidate matrix is informational and non-activating. It compares domain-set overlap using truncated SHA-256 fingerprints rather than publishing raw domain inventories, identifies near-duplicate and high-overlap source sets, and detects cross-policy conflicts. High overlap is retained as a correlation warning; it is not treated as proof of common ancestry or used to discard every domain from either publisher. The active registry still requires two distinct publisher identities and source groups per published domain.

## Automated policy-source overlap audit

`scripts/audit_policy_source_overlap.py` refetches policy-labelled candidate feeds, normalizes domain-only entries, unions files by publisher, calculates same-policy overlap, and reports domains that appear under conflicting policies. Its outputs are `sources/policy_source_overlap.json` and `reports/policy-source-overlap.md`. This is a correlation and conflict signal, not proof of common ancestry or correctness; it never activates sources or publishes rules.


## Deterministic source admission

The source-candidate matrix is consumed by `scripts/auto_activate_sources.py`. Admission is fully deterministic and uses no AI review. It requires strong explicit policy evidence, a non-archived publisher, a supported parser, at least 100 unique domains, an unchanged second observation, and a fresh fetch whose SHA-256 matches the assessed bytes. The exact bytes are then parsed with the production collector before the source registry is changed. Parser failures, drift, weak policy claims and archived publishers remain held as candidates. Lineage uncertainty and shared README references are recorded as warnings rather than automatic vetoes. Newly admitted sources are persisted in the source registry and activation log.

## Rule publication capacity and lifecycle

The three published lists are DIRECT, PROXY and REJECT only. Publication has a hard ceiling of 30,000 unique rules across all three lists. Approved additions that do not fit are stored in `rulesets/pending_queue.json`; the queue is persistent and is promoted in priority/FIFO order when capacity becomes available. Existing published entries are retained by normal builds. Only a lifecycle deletion recorded in `rulesets/deletion_archive.json` can remove an existing entry.

A lifecycle audit is scheduled for every 5,000-rule published-count milestone (5,000, 10,000, 15,000, 20,000, 25,000 and 30,000). A milestone remains pending until its audit completes successfully. Once the published list reaches 30,000, the system also performs a lifecycle audit every 30 days. The 30,000 cap pauses publication, not candidate discovery, deterministic review, or queue storage.

Lifecycle deletion is deliberately conservative. An exact DOMAIN host is eligible only after both Cloudflare and Google DNS-over-HTTPS resolvers return NXDOMAIN for both A and AAAA queries on two separate observations at least 30 days apart, with no intervening DNS recovery. DOMAIN-SUFFIX rules are retained because a suffix root can lack DNS records while valid subdomains still exist. Resolver errors, timeouts, missing evidence, source disappearance, lineage changes, or a single NXDOMAIN observation never authorize deletion. Major technology, cloud, CDN, identity, and Chinese platform suffixes are protected from automatic deletion. All removals are archived with the original policy, rule, timestamps and evidence in `rulesets/deletion_archive.json`; a per-run report is written to `reports/lifecycle/latest.md` and `latest.json`.

To restore a removed entry, copy its ID from the report's selectable recovery list and start the GitHub Actions workflow manually with that ID (or comma-separated IDs) in the `restore_ids` input. A restoration is returned to its original policy when space exists; otherwise it enters the front of the pending queue. The restoration is not re-deleted during the same run. The user-managed `shadowrocket/ss.conf` remains read-only throughout.
