# External domain source audit

- Audit time: 2026-11-01T22:03:41.734718+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: 1489
- Conditional composite rules containing DOMAIN terms (not flattened): 15
- Malformed or unsupported simple domain rules held aside: 0
- Candidates whose apex is governed by an existing domain rule: 19551

## Apex effective policy (first matching original rule wins)

| Effective policy | Candidate apexes |
|---|---:|
| DIRECT | 1570 |
| PROXY | 17856 |
| REJECT | 125 |

## Source-suffix scope policy variation

Candidates whose source suffix scope intersects multiple effective policies: 2

These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.

| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |
|---|---|
| `d.meituan.net` | DIRECT / line 1052 / meituan.net; REJECT / line 116 / data-sdk-uuid-log.d.meituan.net; REJECT / line 118 / maplocatesdksnapshot.d.meituan.net |
| `e.kuaishou.com` | DIRECT / line 673 / kuaishou.com; REJECT / line 59 / open.e.kuaishou.com |

## Same-host shadowed rules

Candidate apexes with later matching rules carrying another policy: 59

The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.

| Candidate | Winner | Later matching rules |
|---|---|---|
| `a.youdao.com` | REJECT line 370 (DOMAIN-SUFFIX a.youdao.com) | DIRECT line 782 (DOMAIN-SUFFIX youdao.com) |
| `ad.12306.cn` | REJECT line 189 (DOMAIN-SUFFIX ad.12306.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `ad.17173.com` | REJECT line 455 (DOMAIN-SUFFIX ad.17173.com) | DIRECT line 809 (DOMAIN-SUFFIX 17173.com) |
| `ad.21cn.com` | REJECT line 458 (DOMAIN-SUFFIX ad.21cn.com) | DIRECT line 812 (DOMAIN-SUFFIX 21cn.com) |
| `ad.api.3g.youku.com` | REJECT line 103 (DOMAIN ad.api.3g.youku.com) | DIRECT line 699 (DOMAIN-SUFFIX youku.com) |
| `ad.cctv.com` | REJECT line 473 (DOMAIN-SUFFIX ad.cctv.com) | DIRECT line 655 (DOMAIN-SUFFIX cctv.com) |
| `ad.cntv.cn` | REJECT line 474 (DOMAIN-SUFFIX ad.cntv.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `ad.csdn.net` | REJECT line 475 (DOMAIN-SUFFIX ad.csdn.net) | DIRECT line 658 (DOMAIN-SUFFIX csdn.net) |
| `ad.ganji.com` | REJECT line 483 (DOMAIN-SUFFIX ad.ganji.com) | DIRECT line 858 (DOMAIN-SUFFIX ganji.com) |
| `ad.mi.com` | REJECT line 501 (DOMAIN-SUFFIX ad.mi.com) | DIRECT line 677 (DOMAIN-SUFFIX mi.com) |
| `ad.qq.com` | REJECT line 505 (DOMAIN-SUFFIX ad.qq.com) | DIRECT line 683 (DOMAIN-SUFFIX qq.com) |
| `ad.sina.com.cn` | REJECT line 507 (DOMAIN-SUFFIX ad.sina.com.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn); DIRECT line 684 (DOMAIN-SUFFIX sina.com.cn) |
| `ad.sohu.com` | REJECT line 508 (DOMAIN-SUFFIX ad.sohu.com) | DIRECT line 685 (DOMAIN-SUFFIX sohu.com) |
| `ad.toutiao.com` | REJECT line 513 (DOMAIN-SUFFIX ad.toutiao.com) | DIRECT line 690 (DOMAIN-SUFFIX toutiao.com) |
| `ad.weibo.com` | REJECT line 515 (DOMAIN-SUFFIX ad.weibo.com) | DIRECT line 694 (DOMAIN-SUFFIX weibo.com) |
| `ad.ximalaya.com` | REJECT line 517 (DOMAIN-SUFFIX ad.ximalaya.com) | DIRECT line 697 (DOMAIN-SUFFIX ximalaya.com) |
| `ad.youku.com` | REJECT line 519 (DOMAIN-SUFFIX ad.youku.com) | DIRECT line 699 (DOMAIN-SUFFIX youku.com) |
| `adashbc.ut.taobao.com` | REJECT line 110 (DOMAIN adashbc.ut.taobao.com) | DIRECT line 687 (DOMAIN-SUFFIX taobao.com) |
| `adashx.m.taobao.com` | REJECT line 121 (DOMAIN adashx.m.taobao.com) | DIRECT line 687 (DOMAIN-SUFFIX taobao.com) |
| `admaster.com.cn` | REJECT line 225 (DOMAIN-SUFFIX admaster.com.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `adview.cn` | REJECT line 142 (DOMAIN-SUFFIX adview.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `adx.yiche.com` | REJECT line 143 (DOMAIN-SUFFIX adx.yiche.com) | DIRECT line 772 (DOMAIN-SUFFIX yiche.com) |
| `amung.us` | REJECT line 233 (DOMAIN-SUFFIX amung.us) | PROXY line 1145 (DOMAIN-SUFFIX us) |
| `anquan.org` | REJECT line 234 (DOMAIN-SUFFIX anquan.org) | PROXY line 1128 (DOMAIN-SUFFIX org) |
| `app-monitor.ele.me` | DIRECT line 847 (DOMAIN-SUFFIX ele.me) | PROXY line 1139 (DOMAIN-SUFFIX me) |
| `cientch.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `client-api.ele.me` | DIRECT line 847 (DOMAIN-SUFFIX ele.me) | PROXY line 1139 (DOMAIN-SUFFIX me) |
| `domob.cn` | REJECT line 149 (DOMAIN-SUFFIX domob.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `game.weibo.cn` | REJECT line 242 (DOMAIN-SUFFIX game.weibo.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn); DIRECT line 1086 (DOMAIN-SUFFIX weibo.cn) |
| `game.weibo.com` | REJECT line 243 (DOMAIN-SUFFIX game.weibo.com) | DIRECT line 694 (DOMAIN-SUFFIX weibo.com) |
| `gdt.qq.com` | REJECT line 113 (DOMAIN gdt.qq.com) | DIRECT line 683 (DOMAIN-SUFFIX qq.com) |
| `grand.ele.me` | DIRECT line 847 (DOMAIN-SUFFIX ele.me) | PROXY line 1139 (DOMAIN-SUFFIX me) |
| `h-adashx.ut.taobao.com` | REJECT line 71 (DOMAIN h-adashx.ut.taobao.com) | DIRECT line 687 (DOMAIN-SUFFIX taobao.com) |
| `hcirentgh.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `hjkhxfh.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `iadsdk.apple.com` | REJECT line 123 (DOMAIN iadsdk.apple.com) | DIRECT line 650 (DOMAIN-SUFFIX apple.com) |
| `inmobi.cn` | REJECT line 155 (DOMAIN-SUFFIX inmobi.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `inmobicdn.cn` | REJECT line 156 (DOMAIN-SUFFIX inmobicdn.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `mobile-pubt.ele.me` | DIRECT line 847 (DOMAIN-SUFFIX ele.me) | PROXY line 1139 (DOMAIN-SUFFIX me) |
| `mobisage.cn` | REJECT line 168 (DOMAIN-SUFFIX mobisage.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `newton-api.ele.me` | DIRECT line 847 (DOMAIN-SUFFIX ele.me) | PROXY line 1139 (DOMAIN-SUFFIX me) |
| `nxet1.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `optimix.cn` | REJECT line 250 (DOMAIN-SUFFIX optimix.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `oth.eve.mdt.qq.com` | REJECT line 92 (DOMAIN oth.eve.mdt.qq.com) | DIRECT line 683 (DOMAIN-SUFFIX qq.com) |
| `pgdt.gtimg.cn` | REJECT line 94 (DOMAIN pgdt.gtimg.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn); DIRECT line 865 (DOMAIN-SUFFIX gtimg.cn) |
| `pjogndc8ixoidna.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `rcd.iqiyi.com` | REJECT line 254 (DOMAIN-SUFFIX rcd.iqiyi.com) | DIRECT line 670 (DOMAIN-SUFFIX iqiyi.com) |
| `s.p.youku.com` | REJECT line 256 (DOMAIN-SUFFIX s.p.youku.com) | DIRECT line 699 (DOMAIN-SUFFIX youku.com) |
| `segment.io` | REJECT line 215 (DOMAIN-SUFFIX segment.io) | PROXY line 1135 (DOMAIN-SUFFIX io) |
| `songlaoban.cn` | REJECT line 258 (DOMAIN-SUFFIX songlaoban.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `splashqqlive.gtimg.com` | REJECT line 96 (DOMAIN splashqqlive.gtimg.com) | DIRECT line 866 (DOMAIN-SUFFIX gtimg.com) |
| `tmead.y.qq.com` | REJECT line 120 (DOMAIN tmead.y.qq.com) | DIRECT line 683 (DOMAIN-SUFFIX qq.com) |
| `tmeadbak.y.qq.com` | REJECT line 109 (DOMAIN tmeadbak.y.qq.com) | DIRECT line 683 (DOMAIN-SUFFIX qq.com) |
| `track.tenjin.io` | REJECT line 100 (DOMAIN track.tenjin.io) | PROXY line 1135 (DOMAIN-SUFFIX io) |
| `tuia.cn` | REJECT line 182 (DOMAIN-SUFFIX tuia.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `voiceads.cn` | REJECT line 223 (DOMAIN-SUFFIX voiceads.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `w5sac788c1.360doc.cn` | REJECT line 283 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `wooboo.com.cn` | REJECT line 262 (DOMAIN-SUFFIX wooboo.com.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |
| `yoyi.com.cn` | REJECT line 268 (DOMAIN-SUFFIX yoyi.com.cn) | DIRECT line 657 (DOMAIN-SUFFIX cn) |

## Interpretation and safety boundary

- The canonical ss.conf is authoritative; original rule order is preserved.
- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.
- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.
- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
