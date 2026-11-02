# External domain source audit

- Audit time: 2026-11-02T01:30:35.196728+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: 1469
- Conditional composite rules containing DOMAIN terms (not flattened): 15
- Malformed or unsupported simple domain rules held aside: 0
- Candidates whose apex is governed by an existing domain rule: 18888

## Apex effective policy (first matching original rule wins)

| Effective policy | Candidate apexes |
|---|---:|
| DIRECT | 1570 |
| PROXY | 17193 |
| REJECT | 125 |

## Source-suffix scope policy variation

Candidates whose source suffix scope intersects multiple effective policies: 2

These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.

| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |
|---|---|
| `d.meituan.net` | DIRECT / line 1566 / meituan.net; REJECT / line 116 / data-sdk-uuid-log.d.meituan.net; REJECT / line 118 / maplocatesdksnapshot.d.meituan.net |
| `e.kuaishou.com` | DIRECT / line 1205 / kuaishou.com; REJECT / line 59 / open.e.kuaishou.com |

## Same-host shadowed rules

Candidate apexes with later matching rules carrying another policy: 52

The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.

| Candidate | Winner | Later matching rules |
|---|---|---|
| `a.youdao.com` | REJECT line 360 (DOMAIN-SUFFIX a.youdao.com) | DIRECT line 1311 (DOMAIN-SUFFIX youdao.com) |
| `ad.12306.cn` | REJECT line 179 (DOMAIN-SUFFIX ad.12306.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `ad.17173.com` | REJECT line 445 (DOMAIN-SUFFIX ad.17173.com) | DIRECT line 1337 (DOMAIN-SUFFIX 17173.com) |
| `ad.21cn.com` | REJECT line 448 (DOMAIN-SUFFIX ad.21cn.com) | DIRECT line 1340 (DOMAIN-SUFFIX 21cn.com) |
| `ad.api.3g.youku.com` | REJECT line 103 (DOMAIN ad.api.3g.youku.com) | DIRECT line 1231 (DOMAIN-SUFFIX youku.com) |
| `ad.cctv.com` | REJECT line 463 (DOMAIN-SUFFIX ad.cctv.com) | DIRECT line 1187 (DOMAIN-SUFFIX cctv.com) |
| `ad.cntv.cn` | REJECT line 464 (DOMAIN-SUFFIX ad.cntv.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `ad.csdn.net` | REJECT line 465 (DOMAIN-SUFFIX ad.csdn.net) | DIRECT line 1190 (DOMAIN-SUFFIX csdn.net) |
| `ad.ganji.com` | REJECT line 473 (DOMAIN-SUFFIX ad.ganji.com) | DIRECT line 1385 (DOMAIN-SUFFIX ganji.com) |
| `ad.mi.com` | REJECT line 491 (DOMAIN-SUFFIX ad.mi.com) | DIRECT line 1209 (DOMAIN-SUFFIX mi.com) |
| `ad.qq.com` | REJECT line 495 (DOMAIN-SUFFIX ad.qq.com) | DIRECT line 1215 (DOMAIN-SUFFIX qq.com) |
| `ad.sina.com.cn` | REJECT line 497 (DOMAIN-SUFFIX ad.sina.com.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn); DIRECT line 1216 (DOMAIN-SUFFIX sina.com.cn) |
| `ad.sohu.com` | REJECT line 498 (DOMAIN-SUFFIX ad.sohu.com) | DIRECT line 1217 (DOMAIN-SUFFIX sohu.com) |
| `ad.toutiao.com` | REJECT line 503 (DOMAIN-SUFFIX ad.toutiao.com) | DIRECT line 1222 (DOMAIN-SUFFIX toutiao.com) |
| `ad.weibo.com` | REJECT line 505 (DOMAIN-SUFFIX ad.weibo.com) | DIRECT line 1226 (DOMAIN-SUFFIX weibo.com) |
| `ad.ximalaya.com` | REJECT line 507 (DOMAIN-SUFFIX ad.ximalaya.com) | DIRECT line 1229 (DOMAIN-SUFFIX ximalaya.com) |
| `ad.youku.com` | REJECT line 509 (DOMAIN-SUFFIX ad.youku.com) | DIRECT line 1231 (DOMAIN-SUFFIX youku.com) |
| `adashbc.ut.taobao.com` | REJECT line 110 (DOMAIN adashbc.ut.taobao.com) | DIRECT line 1219 (DOMAIN-SUFFIX taobao.com) |
| `adashx.m.taobao.com` | REJECT line 121 (DOMAIN adashx.m.taobao.com) | DIRECT line 1219 (DOMAIN-SUFFIX taobao.com) |
| `admaster.com.cn` | REJECT line 215 (DOMAIN-SUFFIX admaster.com.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `adview.cn` | REJECT line 132 (DOMAIN-SUFFIX adview.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `adx.yiche.com` | REJECT line 133 (DOMAIN-SUFFIX adx.yiche.com) | DIRECT line 1301 (DOMAIN-SUFFIX yiche.com) |
| `amung.us` | REJECT line 223 (DOMAIN-SUFFIX amung.us) | PROXY line 661 (DOMAIN-SUFFIX us) |
| `anquan.org` | REJECT line 224 (DOMAIN-SUFFIX anquan.org) | PROXY line 647 (DOMAIN-SUFFIX org) |
| `cientch.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `domob.cn` | REJECT line 139 (DOMAIN-SUFFIX domob.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `game.weibo.cn` | REJECT line 232 (DOMAIN-SUFFIX game.weibo.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn); DIRECT line 1599 (DOMAIN-SUFFIX weibo.cn) |
| `game.weibo.com` | REJECT line 233 (DOMAIN-SUFFIX game.weibo.com) | DIRECT line 1226 (DOMAIN-SUFFIX weibo.com) |
| `gdt.qq.com` | REJECT line 113 (DOMAIN gdt.qq.com) | DIRECT line 1215 (DOMAIN-SUFFIX qq.com) |
| `h-adashx.ut.taobao.com` | REJECT line 71 (DOMAIN h-adashx.ut.taobao.com) | DIRECT line 1219 (DOMAIN-SUFFIX taobao.com) |
| `hcirentgh.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `hjkhxfh.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `iadsdk.apple.com` | REJECT line 123 (DOMAIN iadsdk.apple.com) | DIRECT line 1182 (DOMAIN-SUFFIX apple.com) |
| `inmobi.cn` | REJECT line 145 (DOMAIN-SUFFIX inmobi.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `inmobicdn.cn` | REJECT line 146 (DOMAIN-SUFFIX inmobicdn.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `mobisage.cn` | REJECT line 158 (DOMAIN-SUFFIX mobisage.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `nxet1.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `optimix.cn` | REJECT line 240 (DOMAIN-SUFFIX optimix.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `oth.eve.mdt.qq.com` | REJECT line 92 (DOMAIN oth.eve.mdt.qq.com) | DIRECT line 1215 (DOMAIN-SUFFIX qq.com) |
| `pgdt.gtimg.cn` | REJECT line 94 (DOMAIN pgdt.gtimg.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn); DIRECT line 1391 (DOMAIN-SUFFIX gtimg.cn) |
| `pjogndc8ixoidna.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `rcd.iqiyi.com` | REJECT line 244 (DOMAIN-SUFFIX rcd.iqiyi.com) | DIRECT line 1202 (DOMAIN-SUFFIX iqiyi.com) |
| `s.p.youku.com` | REJECT line 246 (DOMAIN-SUFFIX s.p.youku.com) | DIRECT line 1231 (DOMAIN-SUFFIX youku.com) |
| `songlaoban.cn` | REJECT line 248 (DOMAIN-SUFFIX songlaoban.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `splashqqlive.gtimg.com` | REJECT line 96 (DOMAIN splashqqlive.gtimg.com) | DIRECT line 1392 (DOMAIN-SUFFIX gtimg.com) |
| `tmead.y.qq.com` | REJECT line 120 (DOMAIN tmead.y.qq.com) | DIRECT line 1215 (DOMAIN-SUFFIX qq.com) |
| `tmeadbak.y.qq.com` | REJECT line 109 (DOMAIN tmeadbak.y.qq.com) | DIRECT line 1215 (DOMAIN-SUFFIX qq.com) |
| `tuia.cn` | REJECT line 172 (DOMAIN-SUFFIX tuia.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `voiceads.cn` | REJECT line 213 (DOMAIN-SUFFIX voiceads.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `w5sac788c1.360doc.cn` | REJECT line 273 (DOMAIN-SUFFIX 360doc.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `wooboo.com.cn` | REJECT line 252 (DOMAIN-SUFFIX wooboo.com.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |
| `yoyi.com.cn` | REJECT line 258 (DOMAIN-SUFFIX yoyi.com.cn) | DIRECT line 1189 (DOMAIN-SUFFIX cn) |

## Interpretation and safety boundary

- The canonical ss.conf is authoritative; original rule order is preserved.
- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.
- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.
- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
