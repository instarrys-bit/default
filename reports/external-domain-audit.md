# External domain source audit

- Audit time: 2026-10-31T17:34:13.668217+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: 1759
- Conditional composite rules containing DOMAIN terms (not flattened): 27
- Malformed or unsupported simple domain rules held aside: 0
- Candidates whose apex is governed by an existing domain rule: 2771

## Apex effective policy (first matching original rule wins)

| Effective policy | Candidate apexes |
|---|---:|
| DIRECT | 1175 |
| PROXY | 1333 |
| REJECT | 263 |

## Source-suffix scope policy variation

Candidates whose source suffix scope intersects multiple effective policies: 9

These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.

| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |
|---|---|
| `alitui.weibo.com` | DIRECT / line 1759 / weibo.com; REJECT / line 308 / s.alitui.weibo.com |
| `baidustatic.com` | DIRECT / line 1008 / baidustatic.com; REJECT / line 259 / cpro.baidustatic.com |
| `biz.weibo.com` | DIRECT / line 1759 / weibo.com; REJECT / line 199 / adstrategy.biz.weibo.com; REJECT / line 258 / c.wcpt.biz.weibo.com; REJECT / line 333 / alv.biz.weibo.com; REJECT / line 408 / zc.biz.weibo.com; REJECT / line 473 / c.biz.weibo.com |
| `d.meituan.net` | DIRECT / line 1422 / meituan.net; REJECT / line 96 / al-log.d.meituan.net; REJECT / line 97 / data-sdk-uuid-log.d.meituan.net; REJECT / line 98 / metrics-picture.d.meituan.net; REJECT / line 99 / maplocatesdksnapshot.d.meituan.net |
| `domob.cn` | DIRECT / line 1912 / cn; REJECT / line 608 / sd.domob.cn |
| `e.kuaishou.cn` | DIRECT / line 1912 / cn; REJECT / line 306 / open.e.kuaishou.cn |
| `l.qq.com` | DIRECT / line 1890 / qq.com; REJECT / line 612 / us.l.qq.com |
| `leju.sina.com.cn` | DIRECT / line 1912 / cn; REJECT / line 256 / adm.leju.sina.com.cn |
| `rqd.qq.com` | DIRECT / line 1890 / qq.com; REJECT / line 127 / android.rqd.qq.com |

## Same-host shadowed rules

Candidate apexes with later matching rules carrying another policy: 117

The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.

| Candidate | Winner | Later matching rules |
|---|---|---|
| `09mk.cn` | REJECT line 645 (DOMAIN-SUFFIX 09mk.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `ad.12306.cn` | REJECT line 588 (DOMAIN-SUFFIX ad.12306.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `ad.e.waimai.sankuai.com` | REJECT line 209 (DOMAIN-SUFFIX ad.e.waimai.sankuai.com) | DIRECT line 1436 (DOMAIN-SUFFIX sankuai.com) |
| `ad.intl.xiaomi.com` | REJECT line 297 (DOMAIN-SUFFIX ad.intl.xiaomi.com) | PROXY line 1032 (DOMAIN-SUFFIX intl.xiaomi.com); DIRECT line 1594 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.jiemian.com` | REJECT line 148 (DOMAIN ad.jiemian.com) | DIRECT line 1943 (DOMAIN-SUFFIX jiemian.com) |
| `ad.qq.com` | REJECT line 628 (DOMAIN-SUFFIX ad.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `ad.sina.com.cn` | REJECT line 513 (DOMAIN-SUFFIX ad.sina.com.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `ad.toutiao.com` | REJECT line 514 (DOMAIN-SUFFIX ad.toutiao.com) | DIRECT line 1447 (DOMAIN-SUFFIX toutiao.com) |
| `ad.xiaomi.com` | REJECT line 544 (DOMAIN-SUFFIX ad.xiaomi.com) | DIRECT line 1594 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.zijieapi.com` | REJECT line 466 (DOMAIN-SUFFIX ad.zijieapi.com) | DIRECT line 1355 (DOMAIN-SUFFIX zijieapi.com) |
| `ad1.xiaomi.com` | REJECT line 515 (DOMAIN-SUFFIX ad1.xiaomi.com) | DIRECT line 1594 (DOMAIN-SUFFIX xiaomi.com) |
| `adash-c.ut.taobao.com` | REJECT line 567 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1571 (DOMAIN-SUFFIX taobao.com) |
| `adashbc.ut.taobao.com` | REJECT line 567 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1571 (DOMAIN-SUFFIX taobao.com) |
| `adashx.m.taobao.com` | REJECT line 280 (DOMAIN-SUFFIX adashx.m.taobao.com) | DIRECT line 1571 (DOMAIN-SUFFIX taobao.com) |
| `adashxgc.ut.taobao.com` | REJECT line 567 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1571 (DOMAIN-SUFFIX taobao.com) |
| `adcome.cn` | REJECT line 629 (DOMAIN-SUFFIX adcome.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `adimg.mobile.sina.cn` | REJECT line 255 (DOMAIN-SUFFIX adimg.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `adping.qq.com` | REJECT line 545 (DOMAIN-SUFFIX adping.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adpm.app.qq.com` | REJECT line 467 (DOMAIN-SUFFIX adpm.app.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adrdir.qq.com` | REJECT line 546 (DOMAIN-SUFFIX adrdir.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `ads-img-qc.xhscdn.com` | REJECT line 239 (DOMAIN-SUFFIX ads-img-qc.xhscdn.com) | DIRECT line 1592 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-al.xhscdn.com` | REJECT line 210 (DOMAIN-SUFFIX ads-video-al.xhscdn.com) | DIRECT line 1592 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-qc.xhscdn.com` | REJECT line 211 (DOMAIN-SUFFIX ads-video-qc.xhscdn.com) | DIRECT line 1592 (DOMAIN-SUFFIX xhscdn.com) |
| `ads.youtube.com` | REJECT line 468 (DOMAIN-SUFFIX ads.youtube.com) | PROXY line 1458 (DOMAIN-SUFFIX youtube.com) |
| `adsclick.qq.com` | REJECT line 469 (DOMAIN-SUFFIX adsclick.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adsfile.qq.com` | REJECT line 518 (DOMAIN-SUFFIX adsfile.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adshmmsg.qq.com` | REJECT line 470 (DOMAIN-SUFFIX adshmmsg.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adslvfile.qq.com` | REJECT line 389 (DOMAIN-SUFFIX adslvfile.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adslvseed.qq.com` | REJECT line 390 (DOMAIN-SUFFIX adslvseed.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adsolution.imtt.qq.com` | REJECT line 226 (DOMAIN-SUFFIX adsolution.imtt.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adstextview.qq.com` | REJECT line 299 (DOMAIN-SUFFIX adstextview.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adsview.qq.com` | REJECT line 519 (DOMAIN-SUFFIX adsview.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adsview2.qq.com` | REJECT line 471 (DOMAIN-SUFFIX adsview2.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `aduu.cn` | REJECT line 646 (DOMAIN-SUFFIX aduu.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `adv.app.qq.com` | REJECT line 520 (DOMAIN-SUFFIX adv.app.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adv.sec.intl.miui.com` | PROXY line 1201 (DOMAIN-SUFFIX intl.miui.com) | DIRECT line 1806 (DOMAIN-SUFFIX miui.com) |
| `adver.qq.com` | REJECT line 573 (DOMAIN-SUFFIX adver.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `adview.cn` | REJECT line 631 (DOMAIN-SUFFIX adview.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `afd.l.google.com` | REJECT line 391 (DOMAIN-SUFFIX afd.l.google.com) | PROXY line 1509 (DOMAIN-SUFFIX google.com) |
| `alimama.alicdn.com` | REJECT line 300 (DOMAIN-SUFFIX alimama.alicdn.com) | DIRECT line 1463 (DOMAIN-SUFFIX alicdn.com) |
| `als.baidu.com` | REJECT line 548 (DOMAIN-SUFFIX als.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `atm.sina.com` | REJECT line 576 (DOMAIN-SUFFIX atm.sina.com) | DIRECT line 1814 (DOMAIN-SUFFIX sina.com) |
| `baichuan-sdk.alicdn.com` | REJECT line 212 (DOMAIN-SUFFIX baichuan-sdk.alicdn.com) | DIRECT line 1463 (DOMAIN-SUFFIX alicdn.com) |
| `bugly.qq.com` | REJECT line 128 (DOMAIN-SUFFIX bugly.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `catfront.dianping.com` | REJECT line 240 (DOMAIN-SUFFIX catfront.dianping.com) | DIRECT line 1279 (DOMAIN-SUFFIX dianping.com) |
| `data.mistat.xiaomi.com` | REJECT line 229 (DOMAIN-SUFFIX data.mistat.xiaomi.com) | DIRECT line 1594 (DOMAIN-SUFFIX xiaomi.com) |
| `dcads.sina.com.cn` | REJECT line 336 (DOMAIN-SUFFIX dcads.sina.com.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `dig.bdurl.net` | REJECT line 551 (DOMAIN-SUFFIX dig.bdurl.net) | DIRECT line 1637 (DOMAIN-SUFFIX bdurl.net) |
| `dns.jd.com` | REJECT line 619 (DOMAIN-SUFFIX dns.jd.com) | DIRECT line 1887 (DOMAIN-SUFFIX jd.com) |
| `dp.im.weibo.cn` | REJECT line 526 (DOMAIN-SUFFIX dp.im.weibo.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `dreport.meituan.net` | REJECT line 286 (DOMAIN-SUFFIX dreport.meituan.net) | DIRECT line 1422 (DOMAIN-SUFFIX meituan.net) |
| `dualstack-logs.amap.com` | REJECT line 136 (DOMAIN dualstack-logs.amap.com) | DIRECT line 1768 (DOMAIN-SUFFIX amap.com) |
| `duclick.baidu.com` | REJECT line 337 (DOMAIN-SUFFIX duclick.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `e.kuaishou.com` | REJECT line 527 (DOMAIN-SUFFIX e.kuaishou.com) | DIRECT line 1316 (DOMAIN-SUFFIX kuaishou.com) |
| `e.qq.com` | REJECT line 641 (DOMAIN-SUFFIX e.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `eclick.baidu.com` | REJECT line 395 (DOMAIN-SUFFIX eclick.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `entry.baidu.com` | REJECT line 478 (DOMAIN-SUFFIX entry.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `g1.163.com` | REJECT line 620 (DOMAIN-SUFFIX g1.163.com) | DIRECT line 1835 (DOMAIN-SUFFIX 163.com) |
| `game.weibo.cn` | REJECT line 553 (DOMAIN-SUFFIX game.weibo.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `game.weibo.com` | REJECT line 528 (DOMAIN-SUFFIX game.weibo.com) | DIRECT line 1759 (DOMAIN-SUFFIX weibo.com) |
| `gdfp.gifshow.com` | REJECT line 396 (DOMAIN-SUFFIX gdfp.gifshow.com) | DIRECT line 1398 (DOMAIN-SUFFIX gifshow.com) |
| `gdt.qq.com` | REJECT line 621 (DOMAIN-SUFFIX gdt.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `h-adashx.ut.taobao.com` | REJECT line 567 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1571 (DOMAIN-SUFFIX taobao.com) |
| `hmma.baidu.com` | REJECT line 529 (DOMAIN-SUFFIX hmma.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `httpdns.alicdn.com` | REJECT line 302 (DOMAIN-SUFFIX httpdns.alicdn.com) | DIRECT line 1463 (DOMAIN-SUFFIX alicdn.com) |
| `iadmat.nosdn.127.net` | REJECT line 268 (DOMAIN-SUFFIX iadmat.nosdn.127.net) | DIRECT line 1834 (DOMAIN-SUFFIX 127.net) |
| `iadmusicmat.music.126.net` | REJECT line 191 (DOMAIN-SUFFIX iadmusicmat.music.126.net) | DIRECT line 1833 (DOMAIN-SUFFIX 126.net) |
| `iadmusicmatvideo.music.126.net` | REJECT line 178 (DOMAIN-SUFFIX iadmusicmatvideo.music.126.net) | DIRECT line 1833 (DOMAIN-SUFFIX 126.net) |
| `iadsdk.apple.com` | REJECT line 397 (DOMAIN-SUFFIX iadsdk.apple.com) | DIRECT line 1628 (DOMAIN-SUFFIX apple.com) |
| `im-x.jd.com` | REJECT line 598 (DOMAIN-SUFFIX im-x.jd.com) | DIRECT line 1887 (DOMAIN-SUFFIX jd.com) |
| `imageplus.baidu.com` | REJECT line 290 (DOMAIN-SUFFIX imageplus.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `immob.cn` | REJECT line 642 (DOMAIN-SUFFIX immob.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `inmobi.cn` | REJECT line 634 (DOMAIN-SUFFIX inmobi.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `intely.cn` | REJECT line 635 (DOMAIN-SUFFIX intely.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `log.aliyuncs.com` | REJECT line 135 (DOMAIN-SUFFIX log.aliyuncs.com) | DIRECT line 1250 (DOMAIN-SUFFIX aliyuncs.com) |
| `logs.amap.com` | REJECT line 100 (DOMAIN logs.amap.com) | DIRECT line 1768 (DOMAIN-SUFFIX amap.com) |
| `maizhenai.cn` | REJECT line 580 (DOMAIN-SUFFIX maizhenai.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `mmstat.com` | REJECT line 134 (DOMAIN-SUFFIX mmstat.com) | DIRECT line 1540 (DOMAIN-SUFFIX mmstat.com) |
| `mobads-logs.baidu.com` | REJECT line 250 (DOMAIN-SUFFIX mobads-logs.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `mobads.baidu.com` | REJECT line 399 (DOMAIN-SUFFIX mobads.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `mobileads.google.com` | REJECT line 269 (DOMAIN-SUFFIX mobileads.google.com) | PROXY line 1509 (DOMAIN-SUFFIX google.com) |
| `mtj.baidu.com` | REJECT line 558 (DOMAIN-SUFFIX mtj.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `newspush.sinajs.cn` | REJECT line 305 (DOMAIN-SUFFIX newspush.sinajs.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `nex.163.com` | REJECT line 605 (DOMAIN-SUFFIX nex.163.com) | DIRECT line 1835 (DOMAIN-SUFFIX 163.com) |
| `nsclick.baidu.com` | REJECT line 343 (DOMAIN-SUFFIX nsclick.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `oth.eve.mdt.qq.com` | REJECT line 121 (DOMAIN oth.eve.mdt.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `oth.str.mdt.qq.com` | REJECT line 122 (DOMAIN oth.str.mdt.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `p.twitter.com` | REJECT line 58 (DOMAIN p.twitter.com) | PROXY line 1450 (DOMAIN-SUFFIX twitter.com) |
| `paomifen.cn` | REJECT line 606 (DOMAIN-SUFFIX paomifen.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `pgdt.gtimg.cn` | REJECT line 560 (DOMAIN-SUFFIX pgdt.gtimg.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `pos.baidu.com` | REJECT line 561 (DOMAIN-SUFFIX pos.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `promote.biz.weibo.cn` | REJECT line 272 (DOMAIN-SUFFIX promote.biz.weibo.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `rmonitor.qq.com` | REJECT line 123 (DOMAIN rmonitor.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `sax.sina.cn` | REJECT line 607 (DOMAIN-SUFFIX sax.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `sax.sina.com.cn` | REJECT line 485 (DOMAIN-SUFFIX sax.sina.com.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `scribe.twitter.com` | REJECT line 296 (DOMAIN scribe.twitter.com) | PROXY line 1450 (DOMAIN-SUFFIX twitter.com) |
| `sdkapp.mobile.sina.cn` | REJECT line 251 (DOMAIN-SUFFIX sdkapp.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `sdkapp.uve.weibo.com` | REJECT line 273 (DOMAIN-SUFFIX sdkapp.uve.weibo.com) | DIRECT line 1759 (DOMAIN-SUFFIX weibo.com) |
| `sdkclick.mobile.sina.cn` | REJECT line 218 (DOMAIN-SUFFIX sdkclick.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `songlaoban.cn` | REJECT line 566 (DOMAIN-SUFFIX songlaoban.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `stats.chinaz.com` | REJECT line 403 (DOMAIN-SUFFIX stats.chinaz.com) | DIRECT line 1483 (DOMAIN-SUFFIX chinaz.com) |
| `sugar.zhihu.com` | REJECT line 488 (DOMAIN-SUFFIX sugar.zhihu.com) | DIRECT line 1764 (DOMAIN-SUFFIX zhihu.com) |
| `syndication.twitter.com` | REJECT line 57 (DOMAIN syndication.twitter.com) | PROXY line 1450 (DOMAIN-SUFFIX twitter.com) |
| `t-ads.xiaohongshu.com` | REJECT line 253 (DOMAIN-SUFFIX t-ads.xiaohongshu.com) | DIRECT line 1058 (DOMAIN-SUFFIX xiaohongshu.com) |
| `trace.qq.com` | REJECT line 129 (DOMAIN-SUFFIX trace.qq.com) | DIRECT line 1890 (DOMAIN-SUFFIX qq.com) |
| `tracking.intl.miui.com` | REJECT line 235 (DOMAIN-SUFFIX tracking.intl.miui.com) | PROXY line 1201 (DOMAIN-SUFFIX intl.miui.com); DIRECT line 1806 (DOMAIN-SUFFIX miui.com) |
| `tracking.miui.com` | REJECT line 344 (DOMAIN-SUFFIX tracking.miui.com) | DIRECT line 1806 (DOMAIN-SUFFIX miui.com) |
| `trends.mobile.sina.cn` | REJECT line 254 (DOMAIN-SUFFIX trends.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `ucstat.baidu.com` | REJECT line 406 (DOMAIN-SUFFIX ucstat.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `union.baidu.com` | REJECT line 492 (DOMAIN-SUFFIX union.baidu.com) | DIRECT line 1634 (DOMAIN-SUFFIX baidu.com) |
| `waps.cn` | REJECT line 647 (DOMAIN-SUFFIX waps.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `wbapp.mobile.sina.cn` | REJECT line 274 (DOMAIN-SUFFIX wbapp.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `wbclick.mobile.sina.cn` | REJECT line 236 (DOMAIN-SUFFIX wbclick.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `wbpctips.mobile.sina.cn` | REJECT line 219 (DOMAIN-SUFFIX wbpctips.mobile.sina.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `wooboo.com.cn` | REJECT line 570 (DOMAIN-SUFFIX wooboo.com.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `woodpecker.uc.cn` | REJECT line 407 (DOMAIN-SUFFIX woodpecker.uc.cn) | DIRECT line 1912 (DOMAIN-SUFFIX cn) |
| `zymo.mps.weibo.com` | REJECT line 311 (DOMAIN-SUFFIX zymo.mps.weibo.com) | DIRECT line 1759 (DOMAIN-SUFFIX weibo.com) |

## Interpretation and safety boundary

- The canonical ss.conf is authoritative; original rule order is preserved.
- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.
- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.
- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
