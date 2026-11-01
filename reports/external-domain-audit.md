# External domain source audit

- Audit time: 2026-11-01T16:21:52.087670+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: 1947
- Conditional composite rules containing DOMAIN terms (not flattened): 23
- Malformed or unsupported simple domain rules held aside: 0
- Candidates whose apex is governed by an existing domain rule: 2944

## Apex effective policy (first matching original rule wins)

| Effective policy | Candidate apexes |
|---|---:|
| DIRECT | 1383 |
| PROXY | 1303 |
| REJECT | 258 |

## Source-suffix scope policy variation

Candidates whose source suffix scope intersects multiple effective policies: 12

These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.

| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |
|---|---|
| `alitui.weibo.com` | DIRECT / line 952 / weibo.com; REJECT / line 403 / s.alitui.weibo.com |
| `baidustatic.com` | DIRECT / line 1371 / baidustatic.com; REJECT / line 434 / cpro.baidustatic.com |
| `biz.weibo.com` | DIRECT / line 952 / weibo.com; REJECT / line 322 / c.biz.weibo.com; REJECT / line 371 / zc.biz.weibo.com; REJECT / line 375 / alv.biz.weibo.com; REJECT / line 432 / c.wcpt.biz.weibo.com; REJECT / line 499 / adstrategy.biz.weibo.com |
| `cupid.iqiyi.com` | DIRECT / line 917 / iqiyi.com; REJECT / line 412 / api.cupid.iqiyi.com; REJECT / line 448 / msga.cupid.iqiyi.com |
| `d.meituan.net` | DIRECT / line 1142 / meituan.net; REJECT / line 109 / al-log.d.meituan.net; REJECT / line 129 / metrics-picture.d.meituan.net; REJECT / line 134 / data-sdk-uuid-log.d.meituan.net; REJECT / line 138 / maplocatesdksnapshot.d.meituan.net |
| `domob.cn` | DIRECT / line 741 / cn; REJECT / line 219 / sd.domob.cn |
| `e.kuaishou.cn` | DIRECT / line 741 / cn; REJECT / line 401 / open.e.kuaishou.cn |
| `l.qq.com` | DIRECT / line 768 / qq.com; REJECT / line 224 / us.l.qq.com |
| `l.youku.com` | DIRECT / line 959 / youku.com; REJECT / line 266 / p.l.youku.com; REJECT / line 269 / r.l.youku.com; REJECT / line 277 / v.l.youku.com |
| `leju.sina.com.cn` | DIRECT / line 741 / cn; REJECT / line 429 / adm.leju.sina.com.cn |
| `rqd.qq.com` | DIRECT / line 768 / qq.com; REJECT / line 96 / android.rqd.qq.com |
| `segment.io` | PROXY / line 1749 / segment.io; REJECT / line 293 / api.segment.io |

## Same-host shadowed rules

Candidate apexes with later matching rules carrying another policy: 164

The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.

| Candidate | Winner | Later matching rules |
|---|---|---|
| `09mk.cn` | REJECT line 141 (DOMAIN-SUFFIX 09mk.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `a-dxk.play.api.3g.youku.com` | REJECT line 516 (DOMAIN-SUFFIX a-dxk.play.api.3g.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `actives.youku.com` | REJECT line 372 (DOMAIN-SUFFIX actives.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `ad.12306.cn` | REJECT line 192 (DOMAIN-SUFFIX ad.12306.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `ad.api.3g.youku.com` | REJECT line 408 (DOMAIN-SUFFIX ad.api.3g.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `ad.api.mobile.youku.com` | REJECT line 485 (DOMAIN-SUFFIX ad.api.mobile.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `ad.e.waimai.sankuai.com` | REJECT line 486 (DOMAIN-SUFFIX ad.e.waimai.sankuai.com) | DIRECT line 1153 (DOMAIN-SUFFIX sankuai.com) |
| `ad.intl.xiaomi.com` | REJECT line 390 (DOMAIN-SUFFIX ad.intl.xiaomi.com) | DIRECT line 1068 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.jiemian.com` | REJECT line 73 (DOMAIN ad.jiemian.com) | DIRECT line 1133 (DOMAIN-SUFFIX jiemian.com) |
| `ad.m.iqiyi.com` | REJECT line 281 (DOMAIN-SUFFIX ad.m.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `ad.mobile.youku.com` | REJECT line 409 (DOMAIN-SUFFIX ad.mobile.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `ad.qq.com` | REJECT line 152 (DOMAIN-SUFFIX ad.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `ad.sina.com.cn` | REJECT line 283 (DOMAIN-SUFFIX ad.sina.com.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `ad.toutiao.com` | REJECT line 284 (DOMAIN-SUFFIX ad.toutiao.com) | DIRECT line 1160 (DOMAIN-SUFFIX toutiao.com) |
| `ad.xiaomi.com` | REJECT line 247 (DOMAIN-SUFFIX ad.xiaomi.com) | DIRECT line 1068 (DOMAIN-SUFFIX xiaomi.com) |
| `ad.zijieapi.com` | REJECT line 313 (DOMAIN-SUFFIX ad.zijieapi.com) | DIRECT line 1258 (DOMAIN-SUFFIX zijieapi.com) |
| `ad1.xiaomi.com` | REJECT line 285 (DOMAIN-SUFFIX ad1.xiaomi.com) | DIRECT line 1068 (DOMAIN-SUFFIX xiaomi.com) |
| `adash-c.ut.taobao.com` | REJECT line 276 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1051 (DOMAIN-SUFFIX taobao.com) |
| `adashbc.ut.taobao.com` | REJECT line 276 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1051 (DOMAIN-SUFFIX taobao.com) |
| `adashx.m.taobao.com` | REJECT line 410 (DOMAIN-SUFFIX adashx.m.taobao.com) | DIRECT line 1051 (DOMAIN-SUFFIX taobao.com) |
| `adashxgc.ut.taobao.com` | REJECT line 276 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1051 (DOMAIN-SUFFIX taobao.com) |
| `adcome.cn` | REJECT line 153 (DOMAIN-SUFFIX adcome.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `adimg.mobile.sina.cn` | REJECT line 428 (DOMAIN-SUFFIX adimg.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `adping.qq.com` | REJECT line 248 (DOMAIN-SUFFIX adping.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adpm.app.qq.com` | REJECT line 314 (DOMAIN-SUFFIX adpm.app.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adrdir.qq.com` | REJECT line 249 (DOMAIN-SUFFIX adrdir.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `ads-img-qc.xhscdn.com` | REJECT line 453 (DOMAIN-SUFFIX ads-img-qc.xhscdn.com) | DIRECT line 1066 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-al.xhscdn.com` | REJECT line 487 (DOMAIN-SUFFIX ads-video-al.xhscdn.com) | DIRECT line 1066 (DOMAIN-SUFFIX xhscdn.com) |
| `ads-video-qc.xhscdn.com` | REJECT line 488 (DOMAIN-SUFFIX ads-video-qc.xhscdn.com) | DIRECT line 1066 (DOMAIN-SUFFIX xhscdn.com) |
| `adsclick.qq.com` | REJECT line 317 (DOMAIN-SUFFIX adsclick.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adse.ximalaya.com` | REJECT line 374 (DOMAIN-SUFFIX adse.ximalaya.com) | DIRECT line 1254 (DOMAIN-SUFFIX ximalaya.com) |
| `adsfile.qq.com` | REJECT line 289 (DOMAIN-SUFFIX adsfile.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adshmmsg.qq.com` | REJECT line 318 (DOMAIN-SUFFIX adshmmsg.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adslvfile.qq.com` | REJECT line 348 (DOMAIN-SUFFIX adslvfile.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adslvseed.qq.com` | REJECT line 349 (DOMAIN-SUFFIX adslvseed.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adsolution.imtt.qq.com` | REJECT line 473 (DOMAIN-SUFFIX adsolution.imtt.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adstextview.qq.com` | REJECT line 393 (DOMAIN-SUFFIX adstextview.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adsview.qq.com` | REJECT line 290 (DOMAIN-SUFFIX adsview.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adsview2.qq.com` | REJECT line 319 (DOMAIN-SUFFIX adsview2.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `aduu.cn` | REJECT line 142 (DOMAIN-SUFFIX aduu.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `adv.app.qq.com` | REJECT line 291 (DOMAIN-SUFFIX adv.app.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adver.qq.com` | REJECT line 227 (DOMAIN-SUFFIX adver.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `adview.cn` | REJECT line 155 (DOMAIN-SUFFIX adview.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `afp.iqiyi.com` | REJECT line 250 (DOMAIN-SUFFIX afp.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `alimama.alicdn.com` | REJECT line 394 (DOMAIN-SUFFIX alimama.alicdn.com) | DIRECT line 967 (DOMAIN-SUFFIX alicdn.com) |
| `als.baidu.com` | REJECT line 251 (DOMAIN-SUFFIX als.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `atm.sina.com` | REJECT line 231 (DOMAIN-SUFFIX atm.sina.com) | DIRECT line 851 (DOMAIN-SUFFIX sina.com) |
| `b.smartvideo.youku.com` | REJECT line 474 (DOMAIN-SUFFIX b.smartvideo.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `baichuan-sdk.alicdn.com` | REJECT line 490 (DOMAIN-SUFFIX baichuan-sdk.alicdn.com) | DIRECT line 967 (DOMAIN-SUFFIX alicdn.com) |
| `bugly.qq.com` | REJECT line 232 (DOMAIN-SUFFIX bugly.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `c.uaa.iqiyi.com` | REJECT line 323 (DOMAIN-SUFFIX c.uaa.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `c.yes.youku.com` | REJECT line 324 (DOMAIN-SUFFIX c.yes.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `catfront.dianping.com` | REJECT line 454 (DOMAIN-SUFFIX catfront.dianping.com) | DIRECT line 1203 (DOMAIN-SUFFIX dianping.com) |
| `cloudpush.iqiyi.com` | REJECT line 415 (DOMAIN-SUFFIX cloudpush.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `cm.passport.iqiyi.com` | REJECT line 455 (DOMAIN-SUFFIX cm.passport.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `das.api.youku.com` | REJECT line 377 (DOMAIN-SUFFIX das.api.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `das.mobile.youku.com` | REJECT line 435 (DOMAIN-SUFFIX das.mobile.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `data.mistat.xiaomi.com` | REJECT line 476 (DOMAIN-SUFFIX data.mistat.xiaomi.com) | DIRECT line 1068 (DOMAIN-SUFFIX xiaomi.com) |
| `dcads.sina.com.cn` | REJECT line 378 (DOMAIN-SUFFIX dcads.sina.com.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `dev-push.m.youku.com` | REJECT line 436 (DOMAIN-SUFFIX dev-push.m.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `dig.bdurl.net` | REJECT line 256 (DOMAIN-SUFFIX dig.bdurl.net) | DIRECT line 885 (DOMAIN-SUFFIX bdurl.net) |
| `dl.g.youku.com` | REJECT line 297 (DOMAIN-SUFFIX dl.g.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `dmapp.youku.com` | REJECT line 327 (DOMAIN-SUFFIX dmapp.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `dns.jd.com` | REJECT line 179 (DOMAIN-SUFFIX dns.jd.com) | DIRECT line 762 (DOMAIN-SUFFIX jd.com) |
| `dp.im.weibo.cn` | REJECT line 298 (DOMAIN-SUFFIX dp.im.weibo.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `dreport.meituan.net` | REJECT line 417 (DOMAIN-SUFFIX dreport.meituan.net) | DIRECT line 1142 (DOMAIN-SUFFIX meituan.net) |
| `dualstack-logs.amap.com` | REJECT line 117 (DOMAIN dualstack-logs.amap.com) | DIRECT line 812 (DOMAIN-SUFFIX amap.com) |
| `duclick.baidu.com` | REJECT line 380 (DOMAIN-SUFFIX duclick.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `e.kuaishou.com` | REJECT line 299 (DOMAIN-SUFFIX e.kuaishou.com) | DIRECT line 1220 (DOMAIN-SUFFIX kuaishou.com) |
| `e.qq.com` | REJECT line 147 (DOMAIN-SUFFIX e.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `eclick.baidu.com` | REJECT line 355 (DOMAIN-SUFFIX eclick.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `emoticon.sns.iqiyi.com` | REJECT line 478 (DOMAIN-SUFFIX emoticon.sns.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `entry.baidu.com` | REJECT line 330 (DOMAIN-SUFFIX entry.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `g1.163.com` | REJECT line 180 (DOMAIN-SUFFIX g1.163.com) | DIRECT line 777 (DOMAIN-SUFFIX 163.com) |
| `game.weibo.cn` | REJECT line 258 (DOMAIN-SUFFIX game.weibo.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `game.weibo.com` | REJECT line 300 (DOMAIN-SUFFIX game.weibo.com) | DIRECT line 952 (DOMAIN-SUFFIX weibo.com) |
| `gamecenter.iqiyi.com` | REJECT line 437 (DOMAIN-SUFFIX gamecenter.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `gamex.mobile.youku.com` | REJECT line 479 (DOMAIN-SUFFIX gamex.mobile.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `gdfp.gifshow.com` | REJECT line 357 (DOMAIN-SUFFIX gdfp.gifshow.com) | DIRECT line 1119 (DOMAIN-SUFFIX gifshow.com) |
| `gdt.qq.com` | REJECT line 181 (DOMAIN-SUFFIX gdt.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `h-adashx.ut.taobao.com` | REJECT line 276 (DOMAIN-SUFFIX ut.taobao.com) | DIRECT line 1051 (DOMAIN-SUFFIX taobao.com) |
| `hmma.baidu.com` | REJECT line 301 (DOMAIN-SUFFIX hmma.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `hotchat-im.iqiyi.com` | REJECT line 441 (DOMAIN-SUFFIX hotchat-im.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `httpdns.alicdn.com` | REJECT line 396 (DOMAIN-SUFFIX httpdns.alicdn.com) | DIRECT line 967 (DOMAIN-SUFFIX alicdn.com) |
| `httpdns.baidubce.com` | REJECT line 442 (DOMAIN-SUFFIX httpdns.baidubce.com) | DIRECT line 1188 (DOMAIN-SUFFIX baidubce.com) |
| `hudong.pl.youku.com` | REJECT line 420 (DOMAIN-SUFFIX hudong.pl.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `huodong.pl.youku.com` | REJECT line 445 (DOMAIN-SUFFIX huodong.pl.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `huodong.vip.youku.com` | REJECT line 463 (DOMAIN-SUFFIX huodong.vip.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `hz.youku.com` | REJECT line 236 (DOMAIN-SUFFIX hz.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `iadmat.nosdn.127.net` | REJECT line 446 (DOMAIN-SUFFIX iadmat.nosdn.127.net) | DIRECT line 776 (DOMAIN-SUFFIX 127.net) |
| `iadmusicmat.music.126.net` | REJECT line 508 (DOMAIN-SUFFIX iadmusicmat.music.126.net) | DIRECT line 775 (DOMAIN-SUFFIX 126.net) |
| `iadmusicmatvideo.music.126.net` | REJECT line 525 (DOMAIN-SUFFIX iadmusicmatvideo.music.126.net) | DIRECT line 775 (DOMAIN-SUFFIX 126.net) |
| `iadsdk.apple.com` | REJECT line 358 (DOMAIN-SUFFIX iadsdk.apple.com) | DIRECT line 879 (DOMAIN-SUFFIX apple.com) |
| `ifacelog.iqiyi.com` | REJECT line 399 (DOMAIN-SUFFIX ifacelog.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `im-x.jd.com` | REJECT line 206 (DOMAIN-SUFFIX im-x.jd.com) | DIRECT line 762 (DOMAIN-SUFFIX jd.com) |
| `imageplus.baidu.com` | REJECT line 421 (DOMAIN-SUFFIX imageplus.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `immob.cn` | REJECT line 148 (DOMAIN-SUFFIX immob.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `inmobi.cn` | REJECT line 160 (DOMAIN-SUFFIX inmobi.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `intely.cn` | REJECT line 161 (DOMAIN-SUFFIX intely.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `iyes.youku.com` | REJECT line 303 (DOMAIN-SUFFIX iyes.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `l.ykimg.com` | REJECT line 212 (DOMAIN-SUFFIX l.ykimg.com) | DIRECT line 958 (DOMAIN-SUFFIX ykimg.com) |
| `location.ximalaya.com` | REJECT line 466 (DOMAIN-SUFFIX location.ximalaya.com) | DIRECT line 1254 (DOMAIN-SUFFIX ximalaya.com) |
| `log.aliyuncs.com` | REJECT line 359 (DOMAIN-SUFFIX log.aliyuncs.com) | DIRECT line 1184 (DOMAIN-SUFFIX aliyuncs.com) |
| `logs.amap.com` | REJECT line 69 (DOMAIN logs.amap.com) | DIRECT line 812 (DOMAIN-SUFFIX amap.com) |
| `lstat.youku.com` | REJECT line 332 (DOMAIN-SUFFIX lstat.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `m.yes.youku.com` | REJECT line 334 (DOMAIN-SUFFIX m.yes.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `maizhenai.cn` | REJECT line 237 (DOMAIN-SUFFIX maizhenai.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `mbdlog.iqiyi.com` | REJECT line 360 (DOMAIN-SUFFIX mbdlog.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `mobads-logs.baidu.com` | REJECT line 467 (DOMAIN-SUFFIX mobads-logs.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `mobads.baidu.com` | REJECT line 361 (DOMAIN-SUFFIX mobads.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `mobilemsg.youku.com` | REJECT line 424 (DOMAIN-SUFFIX mobilemsg.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `msg.youku.com` | REJECT line 264 (DOMAIN-SUFFIX msg.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `mtj.baidu.com` | REJECT line 265 (DOMAIN-SUFFIX mtj.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `myes.youku.com` | REJECT line 306 (DOMAIN-SUFFIX myes.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `newspush.sinajs.cn` | REJECT line 400 (DOMAIN-SUFFIX newspush.sinajs.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `nex.163.com` | REJECT line 215 (DOMAIN-SUFFIX nex.163.com) | DIRECT line 777 (DOMAIN-SUFFIX 163.com) |
| `nsclick.baidu.com` | REJECT line 386 (DOMAIN-SUFFIX nsclick.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `oth.eve.mdt.qq.com` | REJECT line 100 (DOMAIN oth.eve.mdt.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `oth.str.mdt.qq.com` | REJECT line 101 (DOMAIN oth.str.mdt.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `p-log.ykimg.com` | REJECT line 335 (DOMAIN-SUFFIX p-log.ykimg.com) | DIRECT line 958 (DOMAIN-SUFFIX ykimg.com) |
| `paomifen.cn` | REJECT line 217 (DOMAIN-SUFFIX paomifen.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `paopao.iqiyi.com` | REJECT line 362 (DOMAIN-SUFFIX paopao.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `passport-log.youku.com` | REJECT line 481 (DOMAIN-SUFFIX passport-log.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `pgdt.gtimg.cn` | REJECT line 267 (DOMAIN-SUFFIX pgdt.gtimg.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `policy.video.iqiyi.com` | REJECT line 482 (DOMAIN-SUFFIX policy.video.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `pos.baidu.com` | REJECT line 268 (DOMAIN-SUFFIX pos.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `promote.biz.weibo.cn` | REJECT line 450 (DOMAIN-SUFFIX promote.biz.weibo.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `push.m.youku.com` | REJECT line 364 (DOMAIN-SUFFIX push.m.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `rcd.iqiyi.com` | REJECT line 270 (DOMAIN-SUFFIX rcd.iqiyi.com) | DIRECT line 917 (DOMAIN-SUFFIX iqiyi.com) |
| `rmonitor.qq.com` | REJECT line 81 (DOMAIN rmonitor.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `s.p.youku.com` | REJECT line 272 (DOMAIN-SUFFIX s.p.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `sax.sina.cn` | REJECT line 218 (DOMAIN-SUFFIX sax.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `sax.sina.com.cn` | REJECT line 337 (DOMAIN-SUFFIX sax.sina.com.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `sdk.m.youku.com` | REJECT line 338 (DOMAIN-SUFFIX sdk.m.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `sdkapp.mobile.sina.cn` | REJECT line 468 (DOMAIN-SUFFIX sdkapp.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `sdkapp.uve.weibo.com` | REJECT line 451 (DOMAIN-SUFFIX sdkapp.uve.weibo.com) | DIRECT line 952 (DOMAIN-SUFFIX weibo.com) |
| `sdkclick.mobile.sina.cn` | REJECT line 497 (DOMAIN-SUFFIX sdkclick.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `songlaoban.cn` | REJECT line 273 (DOMAIN-SUFFIX songlaoban.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `stat.youku.com` | REJECT line 311 (DOMAIN-SUFFIX stat.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `stats.chinaz.com` | REJECT line 365 (DOMAIN-SUFFIX stats.chinaz.com) | DIRECT line 983 (DOMAIN-SUFFIX chinaz.com) |
| `store.tv.api.3g.youku.com` | REJECT line 510 (DOMAIN-SUFFIX store.tv.api.3g.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `store.xl.api.3g.youku.com` | REJECT line 511 (DOMAIN-SUFFIX store.xl.api.3g.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `sugar.zhihu.com` | REJECT line 341 (DOMAIN-SUFFIX sugar.zhihu.com) | DIRECT line 961 (DOMAIN-SUFFIX zhihu.com) |
| `t-ads.xiaohongshu.com` | REJECT line 470 (DOMAIN-SUFFIX t-ads.xiaohongshu.com) | DIRECT line 1397 (DOMAIN-SUFFIX xiaohongshu.com) |
| `tdrec.youku.com` | REJECT line 343 (DOMAIN-SUFFIX tdrec.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `test.ott.youku.com` | REJECT line 405 (DOMAIN-SUFFIX test.ott.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `trace.qq.com` | REJECT line 242 (DOMAIN-SUFFIX trace.qq.com) | DIRECT line 768 (DOMAIN-SUFFIX qq.com) |
| `tracking.intl.miui.com` | REJECT line 483 (DOMAIN-SUFFIX tracking.intl.miui.com) | DIRECT line 839 (DOMAIN-SUFFIX miui.com) |
| `tracking.miui.com` | REJECT line 388 (DOMAIN-SUFFIX tracking.miui.com) | DIRECT line 839 (DOMAIN-SUFFIX miui.com) |
| `trends.mobile.sina.cn` | REJECT line 471 (DOMAIN-SUFFIX trends.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `ucstat.baidu.com` | REJECT line 369 (DOMAIN-SUFFIX ucstat.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `union.baidu.com` | REJECT line 344 (DOMAIN-SUFFIX union.baidu.com) | DIRECT line 881 (DOMAIN-SUFFIX baidu.com) |
| `val.api.youku.com` | REJECT line 389 (DOMAIN-SUFFIX val.api.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `wan.youku.com` | REJECT line 278 (DOMAIN-SUFFIX wan.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `waps.cn` | REJECT line 144 (DOMAIN-SUFFIX waps.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `wbapp.mobile.sina.cn` | REJECT line 452 (DOMAIN-SUFFIX wbapp.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `wbclick.mobile.sina.cn` | REJECT line 484 (DOMAIN-SUFFIX wbclick.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `wbpctips.mobile.sina.cn` | REJECT line 498 (DOMAIN-SUFFIX wbpctips.mobile.sina.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `wooboo.com.cn` | REJECT line 279 (DOMAIN-SUFFIX wooboo.com.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `woodpecker.uc.cn` | REJECT line 370 (DOMAIN-SUFFIX woodpecker.uc.cn) | DIRECT line 741 (DOMAIN-SUFFIX cn) |
| `xdcs-collector.ximalaya.com` | REJECT line 522 (DOMAIN-SUFFIX xdcs-collector.ximalaya.com) | DIRECT line 1254 (DOMAIN-SUFFIX ximalaya.com) |
| `ykatr.youku.com` | REJECT line 345 (DOMAIN-SUFFIX ykatr.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `ykrec.youku.com` | REJECT line 346 (DOMAIN-SUFFIX ykrec.youku.com) | DIRECT line 959 (DOMAIN-SUFFIX youku.com) |
| `zymo.mps.weibo.com` | REJECT line 406 (DOMAIN-SUFFIX zymo.mps.weibo.com) | DIRECT line 952 (DOMAIN-SUFFIX weibo.com) |

## Interpretation and safety boundary

- The canonical ss.conf is authoritative; original rule order is preserved.
- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.
- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.
- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
