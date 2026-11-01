# RULE-SET / ss.conf conflict synchronization

- Config: shadowrocket/ss.conf (read-only)
- Config blob SHA: 4b9f3a60522322b820139774bf65cab9f54ca7c9
- Higher-priority config rules inspected: 1948
- Published rules removed: 89
- Pending queue entries removed: 0
- Ambiguous overlaps retained for review: 1
- Restored: 0

## Removed rules
- cfg-326bec1401e6d3f646fb | DIRECT | DOMAIN-SUFFIX,10010.com | config line 391: DOMAIN-SUFFIX,abc.10010.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-7739291360199761a77a | DIRECT | DOMAIN-SUFFIX,baidupcs.com | config line 407: DOMAIN-SUFFIX,aconsole.baidupcs.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-5200a91c7d40bb665d85 | DIRECT | DOMAIN-SUFFIX,bdimg.com | config line 1085: DOMAIN-SUFFIX,iknow.bdimg.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-bb556f0edacfd850875c | DIRECT | DOMAIN-SUFFIX,bilivideo.cn | config line 658: DOMAIN-SUFFIX,cn,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-6267e509bce00318237c | DIRECT | DOMAIN-SUFFIX,bytedance.com | config line 91: DOMAIN,mssdk-bu.bytedance.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-a18de45ed26dbf220c6d | DIRECT | DOMAIN-SUFFIX,dingtalk.com | config line 412: DOMAIN-SUFFIX,ad-admin.dingtalk.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-03bb2f0c1dd269e12374 | DIRECT | DOMAIN-SUFFIX,douyin.com | config line 663: DOMAIN-SUFFIX,douyin.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-b3f5edb6aedfe1b636fc | DIRECT | DOMAIN-SUFFIX,douyincdn.com | config line 998: DOMAIN-SUFFIX,douyincdn.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-5dc2f9e1291c840142a6 | DIRECT | DOMAIN-SUFFIX,ele.me | config line 856: DOMAIN-SUFFIX,ele.me,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-a9b8f4d2d07ede0515e4 | DIRECT | DOMAIN-SUFFIX,gtimg.com | config line 96: DOMAIN,splashqqlive.gtimg.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-8a6e025ad59ffc991da9 | DIRECT | DOMAIN-SUFFIX,iesdouyin.com | config line 1081: DOMAIN-SUFFIX,iesdouyin.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-450a1198c19b9a759d6b | DIRECT | DOMAIN-SUFFIX,iqiyipic.com | config line 1092: DOMAIN-SUFFIX,iqiyipic.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-fdd22f92c43e7c5c288a | DIRECT | DOMAIN-SUFFIX,kugou.com | config line 422: DOMAIN-SUFFIX,ad-dev.kugou.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-93dce85a71a25a768c11 | DIRECT | DOMAIN-SUFFIX,sandai.net | config line 1311: DOMAIN-SUFFIX,sandai.net,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-331975f7d8ddbd951ff5 | DIRECT | DOMAIN-SUFFIX,sinaimg.cn | config line 658: DOMAIN-SUFFIX,cn,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-b996713a2621784ece95 | DIRECT | DOMAIN-SUFFIX,so.com | config line 1189: DOMAIN-SUFFIX,so.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-a6f5a73037093967aef4 | DIRECT | DOMAIN-SUFFIX,tmall.com | config line 690: DOMAIN-SUFFIX,tmall.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-edf3799cc5f9a4a4d37b | DIRECT | DOMAIN-SUFFIX,xiami.com | config line 767: DOMAIN-SUFFIX,xiami.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-1e9b5a0eb390fad2fcf5 | DIRECT | DOMAIN-SUFFIX,xiami.net | config line 768: DOMAIN-SUFFIX,xiami.net,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-e28e64b763899bbcc6d6 | DIRECT | DOMAIN-SUFFIX,xunlei.com | config line 267: DOMAIN-SUFFIX,xunlei.vip.xunlei.com,REJECT | External rule scope intersects an earlier exact/suffix rule in ss.conf; config wins by first-match order
- cfg-158f1636154aebedab31 | DIRECT | DOMAIN-SUFFIX,zhimg.com | config line 793: DOMAIN-SUFFIX,zhimg.com,DIRECT | Prior first-match rules intersect candidate suffix scope
- cfg-f94626346563132c54e9 | PROXY | DOMAIN-SUFFIX,amazon.com | config line 386: DOMAIN-SUFFIX,aax-cba.amazon.com,REJECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-0255c35cc6520ce5c579 | PROXY | DOMAIN-SUFFIX,ampproject.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-761f52b3ad6d9419a882 | PROXY | DOMAIN-SUFFIX,archive.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-18afc590bbd1b756bc47 | PROXY | DOMAIN-SUFFIX,bandwagonhost.com | config line 1678: DOMAIN-SUFFIX,bandwagonhost.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-89573a1b88c04dc25612 | PROXY | DOMAIN-SUFFIX,blogsmithmedia.com | config line 1840: DOMAIN-SUFFIX,blogsmithmedia.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-d3d841e5dfe9c1eca755 | PROXY | DOMAIN-SUFFIX,bloomberg.com | config line 1551: DOMAIN-SUFFIX,bloomberg.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-f5c14632d474f507db8e | PROXY | DOMAIN-SUFFIX,box.com | config line 1682: DOMAIN-SUFFIX,box.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-b6302eee1bb2e084aaa9 | PROXY | DOMAIN-SUFFIX,cdnst.net | config line 1555: DOMAIN-SUFFIX,cdnst.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-25e64cc2f7f6f91db839 | PROXY | DOMAIN-SUFFIX,disqus.com | config line 1697: DOMAIN-SUFFIX,disqus.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-a8f6431abd6d3eb54f8d | PROXY | DOMAIN-SUFFIX,disquscdn.com | config line 1568: DOMAIN-SUFFIX,disquscdn.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-6876ea5fd998b8fe11c4 | PROXY | DOMAIN-SUFFIX,docker.com | config line 1529: DOMAIN-SUFFIX,docker.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-58ebef5d6942429ec63d | PROXY | DOMAIN-SUFFIX,duckduckgo.com | config line 1514: DOMAIN-SUFFIX,duckduckgo.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-04a0f333b6f274fb11cb | PROXY | DOMAIN-SUFFIX,edgesuite.net | config line 1569: DOMAIN-SUFFIX,edgesuite.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-7728029243401fe271dd | PROXY | DOMAIN-SUFFIX,eurekavpt.com | config line 1570: DOMAIN-SUFFIX,eurekavpt.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-9ae9e8d0fe09b0d726b1 | PROXY | DOMAIN-SUFFIX,fb.me | config line 1355: DOMAIN-SUFFIX,me,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-c47ffb1ff989102c5eac | PROXY | DOMAIN-SUFFIX,fbcdn.net | config line 1503: DOMAIN-SUFFIX,fbcdn.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-ecbffad5a434169406c1 | PROXY | DOMAIN-SUFFIX,flickr.com | config line 1703: DOMAIN-SUFFIX,flickr.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-98f97f6449f2bf6da037 | PROXY | DOMAIN-SUFFIX,flipboard.com | config line 1704: DOMAIN-SUFFIX,flipboard.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-f95a4257d22d332794a3 | PROXY | DOMAIN-SUFFIX,g.co | config line 1365: DOMAIN-SUFFIX,co,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-e451e7eeebd082a61b5f | PROXY | DOMAIN-SUFFIX,gcr.io | config line 1351: DOMAIN-SUFFIX,io,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-51224575a61978f3ff5c | PROXY | DOMAIN-SUFFIX,gongm.in | config line 1350: DOMAIN-SUFFIX,in,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-968b3765109b2e10ae0b | PROXY | DOMAIN-SUFFIX,io.io | config line 1351: DOMAIN-SUFFIX,io,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-60655fd0afb65de36560 | PROXY | DOMAIN-SUFFIX,kakao.co.kr | config line 1354: DOMAIN-SUFFIX,kr,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-89c4ddc5c536fa3219bd | PROXY | DOMAIN-SUFFIX,kakao.com | config line 1601: DOMAIN-SUFFIX,kakao.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-b23b29956c92796f9d02 | PROXY | DOMAIN-SUFFIX,linkedin.com | config line 1603: DOMAIN-SUFFIX,linkedin.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-e48f4e39424705e415f0 | PROXY | DOMAIN-SUFFIX,live.net | config line 1788: DOMAIN-SUFFIX,skyapi.live.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-3c5eb790513574904bd3 | PROXY | DOMAIN-SUFFIX,macrumors.com | config line 1604: DOMAIN-SUFFIX,macrumors.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-cd12044bce7bbfb614f6 | PROXY | DOMAIN-SUFFIX,maven.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-5c93e44f30be88e66032 | PROXY | DOMAIN-SUFFIX,medium.com | config line 1511: DOMAIN-SUFFIX,medium.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-06643e6a120076ebe630 | PROXY | DOMAIN-SUFFIX,mega.nz | config line 1775: DOMAIN-SUFFIX,mega.nz,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-87ee9f82a80b3885a955 | PROXY | DOMAIN-SUFFIX,notion.so | config line 1487: DOMAIN-SUFFIX,notion.so,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-ec14421710364cc8ff64 | PROXY | DOMAIN-SUFFIX,openvpn.net | config line 1726: DOMAIN-SUFFIX,openvpn.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-0304ed6f19bce5031f5a | PROXY | DOMAIN-SUFFIX,periscope.tv | config line 1614: DOMAIN-SUFFIX,periscope.tv,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-f528af92df7f70cdea07 | PROXY | DOMAIN-SUFFIX,pinimg.com | config line 1729: DOMAIN-SUFFIX,pinimg.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-1221254b806b4a3cd692 | PROXY | DOMAIN-SUFFIX,pinterest.com | config line 1730: DOMAIN-SUFFIX,pinterest.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-47fe9731624454752875 | PROXY | DOMAIN-SUFFIX,pixiv.net | config line 1618: DOMAIN-SUFFIX,pixiv.net,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-e14e1e97b28e5850c1c1 | PROXY | DOMAIN-SUFFIX,potato.im | config line 1620: DOMAIN-SUFFIX,potato.im,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-0191f540c8e2f99de82a | PROXY | DOMAIN-SUFFIX,quora.com | config line 1622: DOMAIN-SUFFIX,quora.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-17b03e2e090965f0d2fa | PROXY | DOMAIN-SUFFIX,shadowsocks.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-c428dabab4800be74e9d | PROXY | DOMAIN-SUFFIX,smartmailcloud.com | config line 1628: DOMAIN-SUFFIX,smartmailcloud.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-fc7bc79cb4885c9587cc | PROXY | DOMAIN-SUFFIX,soundcloud.com | config line 1737: DOMAIN-SUFFIX,soundcloud.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-77b67d33136786512467 | PROXY | DOMAIN-SUFFIX,startpage.com | config line 1739: DOMAIN-SUFFIX,startpage.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-dca6d6d6012846b2f42e | PROXY | DOMAIN-SUFFIX,steamcommunity.com | config line 1849: DOMAIN-SUFFIX,steamcommunity.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-e800f3004ed3a3694f9b | PROXY | DOMAIN-SUFFIX,t.co | config line 1365: DOMAIN-SUFFIX,co,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-cd7db84f5d53fedcc871 | PROXY | DOMAIN-SUFFIX,t.me | config line 1355: DOMAIN-SUFFIX,me,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-4337174754fadd1a6a28 | PROXY | DOMAIN-SUFFIX,telegra.ph | config line 1741: DOMAIN-SUFFIX,telegra.ph,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-02bc31d64464dc42e1a5 | PROXY | DOMAIN-SUFFIX,textnow.me | config line 1355: DOMAIN-SUFFIX,me,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-914ae997b8627f9b14e5 | PROXY | DOMAIN-SUFFIX,thepiratebay.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-74e476036d4cbf381446 | PROXY | DOMAIN-SUFFIX,torproject.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-9425df9a1fbbeb9710b0 | PROXY | DOMAIN-SUFFIX,tumblr.co | config line 1365: DOMAIN-SUFFIX,co,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-259b59ce9c4c058d142a | PROXY | DOMAIN-SUFFIX,tumblr.com | config line 1640: DOMAIN-SUFFIX,tumblr.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-b9c3a717d2c34177b407 | PROXY | DOMAIN-SUFFIX,twimg.co | config line 1365: DOMAIN-SUFFIX,co,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-217e2c5064fab4848c68 | PROXY | DOMAIN-SUFFIX,twitch.tv | config line 1528: DOMAIN-SUFFIX,twitch.tv,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-15c2fb13ec0a332a328a | PROXY | DOMAIN-SUFFIX,v2ex.com | config line 949: DOMAIN-SUFFIX,v2ex.com,DIRECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-63642c2f3ae79a4e6d60 | PROXY | DOMAIN-SUFFIX,vimeo.com | config line 1652: DOMAIN-SUFFIX,vimeo.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-9eed0339b3f81ce68d78 | PROXY | DOMAIN-SUFFIX,vine.co | config line 1365: DOMAIN-SUFFIX,co,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-14ab870eb16c2c1b3a77 | PROXY | DOMAIN-SUFFIX,wikileaks.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-b49c275d93b72f8162a3 | PROXY | DOMAIN-SUFFIX,wikimedia.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-492e86c247955fea32f7 | PROXY | DOMAIN-SUFFIX,wikipedia.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-bd17b52bd83730c40b6c | PROXY | DOMAIN-SUFFIX,xvideos.com | config line 1758: DOMAIN-SUFFIX,xvideos.com,PROXY | Prior first-match rules intersect candidate suffix scope
- cfg-89fce022775be0aa8246 | REJECT | DOMAIN,ad-cdn.qingting.fm | config line 927: DOMAIN-SUFFIX,qingting.fm,DIRECT | Prior first-match exact/suffix domain rule
- cfg-86ce172a3194bc1ebe41 | REJECT | DOMAIN,ad.api.moji.com | config line 1138: DOMAIN-SUFFIX,moji.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-b7cb3404111f43a99eab | REJECT | DOMAIN,ads.yahoo.de | config line 1348: DOMAIN-SUFFIX,de,PROXY | Prior first-match exact/suffix domain rule
- cfg-4e68c8c9f93a7585ec4c | REJECT | DOMAIN,adsfilebssdlbig.tx.kugou.com | config line 718: DOMAIN-SUFFIX,kugou.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-afc3ae92aa698d433564 | REJECT | DOMAIN,advertise.baicizhan.com | config line 835: DOMAIN-SUFFIX,baicizhan.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-626ff39e334408851f97 | REJECT | DOMAIN,advertise.baicizhan.org | config line 1344: DOMAIN-SUFFIX,org,PROXY | Prior first-match exact/suffix domain rule
- cfg-3c135f9b13ee1e0e0402 | REJECT | DOMAIN,ggx03.miguvideo.com | config line 1010: DOMAIN-SUFFIX,miguvideo.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-be532deac336944d3b78 | REJECT | DOMAIN,kad.gotokeep.com | config line 873: DOMAIN-SUFFIX,gotokeep.com,DIRECT | Prior first-match exact/suffix domain rule

## Already archived entries suppressed
- None

## Retained ambiguous overlaps
- PROXY | DOMAIN-SUFFIX,thefacebook.com | REVIEW | Prior DOMAIN-KEYWORD may match this candidate

## Restoration
- None

The script never writes to shadowrocket/ss.conf. A config-scope archive entry is not restored automatically; restoration is opt-in and rechecked against all exact/suffix overlaps and skip-proxy entries.
