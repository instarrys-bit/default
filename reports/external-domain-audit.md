# External domain source audit

- Audit time: 2026-11-01T16:34:12.297423+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: 1937
- Conditional composite rules containing DOMAIN terms (not flattened): 25
- Malformed or unsupported simple domain rules held aside: 0
- Candidates whose apex is governed by an existing domain rule: 2944

## Apex effective policy (first matching original rule wins)

| Effective policy | Candidate apexes |
|---|---:|
| DIRECT | 1383 |
| PROXY | 1306 |
| REJECT | 255 |

## Source-suffix scope policy variation

Candidates whose source suffix scope intersects multiple effective policies: 12

These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.

| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |
|---|---|
| `alitui.weibo.com` | DIRECT / line 925 / weibo.com; REJECT / line 386 / s.alitui.weibo.com |
| `baidustatic.com` | DIRECT / line 1343 / baidustatic.com; REJECT / line 417 / cpro.baidustatic.com |
| `biz.weibo.com` | DIRECT / line 925 / weibo.com; REJECT / line 307 / c.biz.weibo.com; REJECT / line 354 / zc.biz.weibo.com; REJECT / line 358 / alv.biz.weibo.com; REJECT / line 415 / c.wcpt.biz.weibo.com; REJECT / line 482 / adstrategy.biz.weibo.com |
| `cupid.iqiyi.com` | DIRECT / line 890 / iqiyi.com; REJECT / line 395 / api.cupid.iqiyi.com; REJECT / line 431 / msga.cupid.iqiyi.com |
| `d.meituan.net` | DIRECT / line 1114 / meituan.net; REJECT / line 99 / al-log.d.meituan.net; REJECT / line 118 / metrics-picture.d.meituan.net; REJECT / line 123 / data-sdk-uuid-log.d.meituan.net; REJECT / line 125 / maplocatesdksnapshot.d.meituan.net |
| `domob.cn` | DIRECT / line 714 / cn; REJECT / line 204 / sd.domob.cn |
| `e.kuaishou.cn` | DIRECT / line 714 / cn; REJECT / line 384 / open.e.kuaishou.cn |
| `l.qq.com` | DIRECT / line 741 / qq.com; REJECT / line 209 / us.l.qq.com |
| `l.youku.com` | DIRECT / line 932 / youku.com; REJECT / line 251 / p.l.youku.com; REJECT / line 254 / r.l.youku.com; REJECT / line 262 / v.l.youku.com |
| `leju.sina.com.cn` | DIRECT / line 714 / cn; REJECT / line 412 / adm.leju.sina.com.cn |
| `rqd.qq.com` | DIRECT / line 741 / qq.com; REJECT / line 88 / android.rqd.qq.com |
| `segment.io` | PROXY / line 1724 / segment.io; REJECT / line 278 / api.segment.io |

## Same-host shadowed rules

Candidate apexes with later matching rules carrying another policy: 164

The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.

| Candidate | Winner | Later matching rules |
|---|---|---|
| `09mk.cn` | REJECT line 127 (DOMAIN-SUFFIX 09mk.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `a-dxk.play.api.3g.youku.com` | REJECT line 499 (DOMAIN-SUFFIX a-dxk.play.api.3g.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `actives.youku.com` | REJECT line 355 (DOMAIN-SUFFIX actives.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `ad.12306.cn` | REJECT line 177 (DOMAIN-SUFFIX ad.12306.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `ad.api.3g.youku.com` | REJECT line 391 (DOMAIN-SUFFIX ad.api.3g.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `ad.api.mobile.youku.com` | REJECT line 468 (DOMAIN-SUFFIX ad.api.mobile.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `ad.e.waimai.sankuai.com` | REJECT line 469 (DOMAIN-SUFFIX ad.e.waimai.sankuai.com) | DIRECT line 1125 (DOMAIN-SUFFIX sankuai.com) |
| `ad.intl.xiaomi.com` | REJECT line 373 (DOMAIN-SUFFIX ad.intl.xiaomi.com) | DIRECT line 1041 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.jiemian.com` | REJECT line 66 (DOMAIN ad.jiemian.com) | DIRECT line 1105 (DOMAIN-SUFFIX jiemian.com) |
| `ad.m.iqiyi.com` | REJECT line 266 (DOMAIN-SUFFIX ad.m.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `ad.mobile.youku.com` | REJECT line 392 (DOMAIN-SUFFIX ad.mobile.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `ad.qq.com` | REJECT line 138 (DOMAIN-SUFFIX ad.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `ad.sina.com.cn` | REJECT line 268 (DOMAIN-SUFFIX ad.sina.com.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `ad.toutiao.com` | REJECT line 269 (DOMAIN-SUFFIX ad.toutiao.com) | DIRECT line 1132 (DOMAIN-SUFFIX toutiao.com) |
| `ad.xiaomi.com` | REJECT line 231 (DOMAIN-SUFFIX ad.xiaomi.com) | DIRECT line 1041 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.zijieapi.com` | REJECT line 298 (DOMAIN-SUFFIX ad.zijieapi.com) | DIRECT line 1230 (DOMAIN-SUFFIX zijieapi.com) |
| `ad1.xiaomi.com` | REJECT line 270 (DOMAIN-SUFFIX ad1.xiaomi.com) | DIRECT line 1041 (DOMAIN-SUFFIX xiaomi.com) |
| `adash-c.ut.taobao.com` | REJECT line 261 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1024 (DOMAIN-SUFFIX taobao.com) |
| `adashbc.ut.taobao.com` | REJECT line 261 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1024 (DOMAIN-SUFFIX taobao.com) |
| `adashx.m.taobao.com` | REJECT line 393 (DOMAIN-SUFFIX adashx.m.taobao.com) | DIRECT line 1024 (DOMAIN-SUFFIX taobao.com) |
| `adashxgc.ut.taobao.com` | REJECT line 261 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1024 (DOMAIN-SUFFIX taobao.com) |
| `adcome.cn` | REJECT line 139 (DOMAIN-SUFFIX adcome.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `adimg.mobile.sina.cn` | REJECT line 411 (DOMAIN-SUFFIX adimg.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `adping.qq.com` | REJECT line 232 (DOMAIN-SUFFIX adping.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adpm.app.qq.com` | REJECT line 299 (DOMAIN-SUFFIX adpm.app.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adrdir.qq.com` | REJECT line 233 (DOMAIN-SUFFIX adrdir.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `ads-img-qc.xhscdn.com` | REJECT line 436 (DOMAIN-SUFFIX ads-img-qc.xhscdn.com) | DIRECT line 1039 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-al.xhscdn.com` | REJECT line 470 (DOMAIN-SUFFIX ads-video-al.xhscdn.com) | DIRECT line 1039 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-qc.xhscdn.com` | REJECT line 471 (DOMAIN-SUFFIX ads-video-qc.xhscdn.com) | DIRECT line 1039 (DOMAIN-SUFFIX xhscdn.com) |
| `adsclick.qq.com` | REJECT line 302 (DOMAIN-SUFFIX adsclick.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adse.ximalaya.com` | REJECT line 357 (DOMAIN-SUFFIX adse.ximalaya.com) | DIRECT line 1226 (DOMAIN-SUFFIX ximalaya.com) |
| `adsfile.qq.com` | REJECT line 274 (DOMAIN-SUFFIX adsfile.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adshmmsg.qq.com` | REJECT line 303 (DOMAIN-SUFFIX adshmmsg.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adslvfile.qq.com` | REJECT line 331 (DOMAIN-SUFFIX adslvfile.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adslvseed.qq.com` | REJECT line 332 (DOMAIN-SUFFIX adslvseed.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adsolution.imtt.qq.com` | REJECT line 456 (DOMAIN-SUFFIX adsolution.imtt.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adstextview.qq.com` | REJECT line 376 (DOMAIN-SUFFIX adstextview.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adsview.qq.com` | REJECT line 275 (DOMAIN-SUFFIX adsview.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adsview2.qq.com` | REJECT line 304 (DOMAIN-SUFFIX adsview2.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `aduu.cn` | REJECT line 128 (DOMAIN-SUFFIX aduu.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `adv.app.qq.com` | REJECT line 276 (DOMAIN-SUFFIX adv.app.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adver.qq.com` | REJECT line 212 (DOMAIN-SUFFIX adver.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `adview.cn` | REJECT line 141 (DOMAIN-SUFFIX adview.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `afp.iqiyi.com` | REJECT line 234 (DOMAIN-SUFFIX afp.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `alimama.alicdn.com` | REJECT line 377 (DOMAIN-SUFFIX alimama.alicdn.com) | DIRECT line 940 (DOMAIN-SUFFIX alicdn.com) |
| `als.baidu.com` | REJECT line 235 (DOMAIN-SUFFIX als.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `atm.sina.com` | REJECT line 216 (DOMAIN-SUFFIX atm.sina.com) | DIRECT line 824 (DOMAIN-SUFFIX sina.com) |
| `b.smartvideo.youku.com` | REJECT line 457 (DOMAIN-SUFFIX b.smartvideo.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `baichuan-sdk.alicdn.com` | REJECT line 473 (DOMAIN-SUFFIX baichuan-sdk.alicdn.com) | DIRECT line 940 (DOMAIN-SUFFIX alicdn.com) |
| `bugly.qq.com` | REJECT line 217 (DOMAIN-SUFFIX bugly.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `c.uaa.iqiyi.com` | REJECT line 308 (DOMAIN-SUFFIX c.uaa.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `c.yes.youku.com` | REJECT line 309 (DOMAIN-SUFFIX c.yes.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `catfront.dianping.com` | REJECT line 437 (DOMAIN-SUFFIX catfront.dianping.com) | DIRECT line 1175 (DOMAIN-SUFFIX dianping.com) |
| `cloudpush.iqiyi.com` | REJECT line 398 (DOMAIN-SUFFIX cloudpush.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `cm.passport.iqiyi.com` | REJECT line 438 (DOMAIN-SUFFIX cm.passport.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `das.api.youku.com` | REJECT line 360 (DOMAIN-SUFFIX das.api.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `das.mobile.youku.com` | REJECT line 418 (DOMAIN-SUFFIX das.mobile.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `data.mistat.xiaomi.com` | REJECT line 459 (DOMAIN-SUFFIX data.mistat.xiaomi.com) | DIRECT line 1041 (DOMAIN-SUFFIX xiaomi.com) |
| `dcads.sina.com.cn` | REJECT line 361 (DOMAIN-SUFFIX dcads.sina.com.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `dev-push.m.youku.com` | REJECT line 419 (DOMAIN-SUFFIX dev-push.m.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `dig.bdurl.net` | REJECT line 241 (DOMAIN-SUFFIX dig.bdurl.net) | DIRECT line 858 (DOMAIN-SUFFIX bdurl.net) |
| `dl.g.youku.com` | REJECT line 282 (DOMAIN-SUFFIX dl.g.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `dmapp.youku.com` | REJECT line 312 (DOMAIN-SUFFIX dmapp.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `dns.jd.com` | REJECT line 164 (DOMAIN-SUFFIX dns.jd.com) | DIRECT line 735 (DOMAIN-SUFFIX jd.com) |
| `dp.im.weibo.cn` | REJECT line 283 (DOMAIN-SUFFIX dp.im.weibo.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `dreport.meituan.net` | REJECT line 400 (DOMAIN-SUFFIX dreport.meituan.net) | DIRECT line 1114 (DOMAIN-SUFFIX meituan.net) |
| `dualstack-logs.amap.com` | REJECT line 107 (DOMAIN dualstack-logs.amap.com) | DIRECT line 785 (DOMAIN-SUFFIX amap.com) |
| `duclick.baidu.com` | REJECT line 363 (DOMAIN-SUFFIX duclick.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `e.kuaishou.com` | REJECT line 284 (DOMAIN-SUFFIX e.kuaishou.com) | DIRECT line 1192 (DOMAIN-SUFFIX kuaishou.com) |
| `e.qq.com` | REJECT line 133 (DOMAIN-SUFFIX e.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `eclick.baidu.com` | REJECT line 338 (DOMAIN-SUFFIX eclick.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `emoticon.sns.iqiyi.com` | REJECT line 461 (DOMAIN-SUFFIX emoticon.sns.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `entry.baidu.com` | REJECT line 315 (DOMAIN-SUFFIX entry.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `g1.163.com` | REJECT line 165 (DOMAIN-SUFFIX g1.163.com) | DIRECT line 750 (DOMAIN-SUFFIX 163.com) |
| `game.weibo.cn` | REJECT line 243 (DOMAIN-SUFFIX game.weibo.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `game.weibo.com` | REJECT line 285 (DOMAIN-SUFFIX game.weibo.com) | DIRECT line 925 (DOMAIN-SUFFIX weibo.com) |
| `gamecenter.iqiyi.com` | REJECT line 420 (DOMAIN-SUFFIX gamecenter.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `gamex.mobile.youku.com` | REJECT line 462 (DOMAIN-SUFFIX gamex.mobile.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `gdfp.gifshow.com` | REJECT line 340 (DOMAIN-SUFFIX gdfp.gifshow.com) | DIRECT line 1091 (DOMAIN-SUFFIX gifshow.com) |
| `gdt.qq.com` | REJECT line 166 (DOMAIN-SUFFIX gdt.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `h-adashx.ut.taobao.com` | REJECT line 261 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1024 (DOMAIN-SUFFIX taobao.com) |
| `hmma.baidu.com` | REJECT line 286 (DOMAIN-SUFFIX hmma.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `hotchat-im.iqiyi.com` | REJECT line 424 (DOMAIN-SUFFIX hotchat-im.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `httpdns.alicdn.com` | REJECT line 379 (DOMAIN-SUFFIX httpdns.alicdn.com) | DIRECT line 940 (DOMAIN-SUFFIX alicdn.com) |
| `httpdns.baidubce.com` | REJECT line 425 (DOMAIN-SUFFIX httpdns.baidubce.com) | DIRECT line 1160 (DOMAIN-SUFFIX baidubce.com) |
| `hudong.pl.youku.com` | REJECT line 403 (DOMAIN-SUFFIX hudong.pl.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `huodong.pl.youku.com` | REJECT line 428 (DOMAIN-SUFFIX huodong.pl.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `huodong.vip.youku.com` | REJECT line 446 (DOMAIN-SUFFIX huodong.vip.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `hz.youku.com` | REJECT line 221 (DOMAIN-SUFFIX hz.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `iadmat.nosdn.127.net` | REJECT line 429 (DOMAIN-SUFFIX iadmat.nosdn.127.net) | DIRECT line 749 (DOMAIN-SUFFIX 127.net) |
| `iadmusicmat.music.126.net` | REJECT line 491 (DOMAIN-SUFFIX iadmusicmat.music.126.net) | DIRECT line 748 (DOMAIN-SUFFIX 126.net) |
| `iadmusicmatvideo.music.126.net` | REJECT line 508 (DOMAIN-SUFFIX iadmusicmatvideo.music.126.net) | DIRECT line 748 (DOMAIN-SUFFIX 126.net) |
| `iadsdk.apple.com` | REJECT line 341 (DOMAIN-SUFFIX iadsdk.apple.com) | DIRECT line 852 (DOMAIN-SUFFIX apple.com) |
| `ifacelog.iqiyi.com` | REJECT line 382 (DOMAIN-SUFFIX ifacelog.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `im-x.jd.com` | REJECT line 191 (DOMAIN-SUFFIX im-x.jd.com) | DIRECT line 735 (DOMAIN-SUFFIX jd.com) |
| `imageplus.baidu.com` | REJECT line 404 (DOMAIN-SUFFIX imageplus.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `immob.cn` | REJECT line 134 (DOMAIN-SUFFIX immob.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `inmobi.cn` | REJECT line 146 (DOMAIN-SUFFIX inmobi.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `intely.cn` | REJECT line 147 (DOMAIN-SUFFIX intely.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `iyes.youku.com` | REJECT line 288 (DOMAIN-SUFFIX iyes.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `l.ykimg.com` | REJECT line 197 (DOMAIN-SUFFIX l.ykimg.com) | DIRECT line 931 (DOMAIN-SUFFIX ykimg.com) |
| `location.ximalaya.com` | REJECT line 449 (DOMAIN-SUFFIX location.ximalaya.com) | DIRECT line 1226 (DOMAIN-SUFFIX ximalaya.com) |
| `log.aliyuncs.com` | REJECT line 342 (DOMAIN-SUFFIX log.aliyuncs.com) | DIRECT line 1156 (DOMAIN-SUFFIX aliyuncs.com) |
| `logs.amap.com` | REJECT line 63 (DOMAIN logs.amap.com) | DIRECT line 785 (DOMAIN-SUFFIX amap.com) |
| `lstat.youku.com` | REJECT line 317 (DOMAIN-SUFFIX lstat.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `m.yes.youku.com` | REJECT line 319 (DOMAIN-SUFFIX m.yes.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `maizhenai.cn` | REJECT line 222 (DOMAIN-SUFFIX maizhenai.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `mbdlog.iqiyi.com` | REJECT line 343 (DOMAIN-SUFFIX mbdlog.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `mobads-logs.baidu.com` | REJECT line 450 (DOMAIN-SUFFIX mobads-logs.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `mobads.baidu.com` | REJECT line 344 (DOMAIN-SUFFIX mobads.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `mobilemsg.youku.com` | REJECT line 407 (DOMAIN-SUFFIX mobilemsg.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `msg.youku.com` | REJECT line 249 (DOMAIN-SUFFIX msg.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `mtj.baidu.com` | REJECT line 250 (DOMAIN-SUFFIX mtj.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `myes.youku.com` | REJECT line 291 (DOMAIN-SUFFIX myes.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `newspush.sinajs.cn` | REJECT line 383 (DOMAIN-SUFFIX newspush.sinajs.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `nex.163.com` | REJECT line 200 (DOMAIN-SUFFIX nex.163.com) | DIRECT line 750 (DOMAIN-SUFFIX 163.com) |
| `nsclick.baidu.com` | REJECT line 369 (DOMAIN-SUFFIX nsclick.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `oth.eve.mdt.qq.com` | REJECT line 91 (DOMAIN oth.eve.mdt.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `oth.str.mdt.qq.com` | REJECT line 92 (DOMAIN oth.str.mdt.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `p-log.ykimg.com` | REJECT line 320 (DOMAIN-SUFFIX p-log.ykimg.com) | DIRECT line 931 (DOMAIN-SUFFIX ykimg.com) |
| `paomifen.cn` | REJECT line 202 (DOMAIN-SUFFIX paomifen.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `paopao.iqiyi.com` | REJECT line 345 (DOMAIN-SUFFIX paopao.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `passport-log.youku.com` | REJECT line 464 (DOMAIN-SUFFIX passport-log.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `pgdt.gtimg.cn` | REJECT line 252 (DOMAIN-SUFFIX pgdt.gtimg.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `policy.video.iqiyi.com` | REJECT line 465 (DOMAIN-SUFFIX policy.video.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `pos.baidu.com` | REJECT line 253 (DOMAIN-SUFFIX pos.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `promote.biz.weibo.cn` | REJECT line 433 (DOMAIN-SUFFIX promote.biz.weibo.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `push.m.youku.com` | REJECT line 347 (DOMAIN-SUFFIX push.m.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `rcd.iqiyi.com` | REJECT line 255 (DOMAIN-SUFFIX rcd.iqiyi.com) | DIRECT line 890 (DOMAIN-SUFFIX iqiyi.com) |
| `rmonitor.qq.com` | REJECT line 74 (DOMAIN rmonitor.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `s.p.youku.com` | REJECT line 257 (DOMAIN-SUFFIX s.p.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `sax.sina.cn` | REJECT line 203 (DOMAIN-SUFFIX sax.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `sax.sina.com.cn` | REJECT line 321 (DOMAIN-SUFFIX sax.sina.com.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `sdk.m.youku.com` | REJECT line 322 (DOMAIN-SUFFIX sdk.m.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `sdkapp.mobile.sina.cn` | REJECT line 451 (DOMAIN-SUFFIX sdkapp.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `sdkapp.uve.weibo.com` | REJECT line 434 (DOMAIN-SUFFIX sdkapp.uve.weibo.com) | DIRECT line 925 (DOMAIN-SUFFIX weibo.com) |
| `sdkclick.mobile.sina.cn` | REJECT line 480 (DOMAIN-SUFFIX sdkclick.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `songlaoban.cn` | REJECT line 258 (DOMAIN-SUFFIX songlaoban.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `stat.youku.com` | REJECT line 296 (DOMAIN-SUFFIX stat.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `stats.chinaz.com` | REJECT line 348 (DOMAIN-SUFFIX stats.chinaz.com) | DIRECT line 956 (DOMAIN-SUFFIX chinaz.com) |
| `store.tv.api.3g.youku.com` | REJECT line 493 (DOMAIN-SUFFIX store.tv.api.3g.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `store.xl.api.3g.youku.com` | REJECT line 494 (DOMAIN-SUFFIX store.xl.api.3g.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `sugar.zhihu.com` | REJECT line 324 (DOMAIN-SUFFIX sugar.zhihu.com) | DIRECT line 934 (DOMAIN-SUFFIX zhihu.com) |
| `t-ads.xiaohongshu.com` | REJECT line 453 (DOMAIN-SUFFIX t-ads.xiaohongshu.com) | DIRECT line 1369 (DOMAIN-SUFFIX xiaohongshu.com) |
| `tdrec.youku.com` | REJECT line 326 (DOMAIN-SUFFIX tdrec.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `test.ott.youku.com` | REJECT line 388 (DOMAIN-SUFFIX test.ott.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `trace.qq.com` | REJECT line 226 (DOMAIN-SUFFIX trace.qq.com) | DIRECT line 741 (DOMAIN-SUFFIX qq.com) |
| `tracking.intl.miui.com` | REJECT line 466 (DOMAIN-SUFFIX tracking.intl.miui.com) | DIRECT line 812 (DOMAIN-SUFFIX miui.com) |
| `tracking.miui.com` | REJECT line 371 (DOMAIN-SUFFIX tracking.miui.com) | DIRECT line 812 (DOMAIN-SUFFIX miui.com) |
| `trends.mobile.sina.cn` | REJECT line 454 (DOMAIN-SUFFIX trends.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `ucstat.baidu.com` | REJECT line 352 (DOMAIN-SUFFIX ucstat.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `union.baidu.com` | REJECT line 327 (DOMAIN-SUFFIX union.baidu.com) | DIRECT line 854 (DOMAIN-SUFFIX baidu.com) |
| `val.api.youku.com` | REJECT line 372 (DOMAIN-SUFFIX val.api.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `wan.youku.com` | REJECT line 263 (DOMAIN-SUFFIX wan.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `waps.cn` | REJECT line 130 (DOMAIN-SUFFIX waps.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `wbapp.mobile.sina.cn` | REJECT line 435 (DOMAIN-SUFFIX wbapp.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `wbclick.mobile.sina.cn` | REJECT line 467 (DOMAIN-SUFFIX wbclick.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `wbpctips.mobile.sina.cn` | REJECT line 481 (DOMAIN-SUFFIX wbpctips.mobile.sina.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `wooboo.com.cn` | REJECT line 264 (DOMAIN-SUFFIX wooboo.com.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `woodpecker.uc.cn` | REJECT line 353 (DOMAIN-SUFFIX woodpecker.uc.cn) | DIRECT line 714 (DOMAIN-SUFFIX cn) |
| `xdcs-collector.ximalaya.com` | REJECT line 505 (DOMAIN-SUFFIX xdcs-collector.ximalaya.com) | DIRECT line 1226 (DOMAIN-SUFFIX ximalaya.com) |
| `ykatr.youku.com` | REJECT line 328 (DOMAIN-SUFFIX ykatr.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `ykrec.youku.com` | REJECT line 329 (DOMAIN-SUFFIX ykrec.youku.com) | DIRECT line 932 (DOMAIN-SUFFIX youku.com) |
| `zymo.mps.weibo.com` | REJECT line 389 (DOMAIN-SUFFIX zymo.mps.weibo.com) | DIRECT line 925 (DOMAIN-SUFFIX weibo.com) |

## Interpretation and safety boundary

- The canonical ss.conf is authoritative; original rule order is preserved.
- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.
- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.
- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
