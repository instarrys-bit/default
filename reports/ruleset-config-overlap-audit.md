# RULE-SET / user-config overlap audit

- Authority: read-only shadowrocket/ss.conf
- First RULE-SET line: 653
- Earlier active rules: 623
- Ledger candidates: 934
- Result: PASS

## Status counts

- ALREADY_COVERED: 9
- CONDITIONAL_POTENTIAL: 15
- CONFLICT: 35
- NOT_COVERED_BY_PRIOR_DOMAIN_RULES: 875

## Findings

- 126.net (DIRECT): CONFLICT — line 489: Prior first-match rules produce a conflicting policy within suffix scope
- 127.net (DIRECT): CONFLICT — line 427: Prior first-match rules produce a conflicting policy within suffix scope
- 163.com (DIRECT): CONFLICT — line 111: Prior first-match rules produce a conflicting policy within suffix scope
- 1e100.net (PROXY): CONDITIONAL_POTENTIAL — line 28: Prior compound rule contains a matching domain operand; other operands are not evaluated
- 95516.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- abchina.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- alicdn.com (DIRECT): CONFLICT — line 375: Prior first-match rules produce a conflicting policy within suffix scope
- alipay.com (DIRECT): CONFLICT — line 93: Prior first-match rules produce a conflicting policy within suffix scope
- alipayobjects.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- aliyuncs.com (DIRECT): CONFLICT — line 453: Prior first-match rules produce a conflicting policy within suffix scope
- amap.com (DIRECT): CONFLICT — line 105: Prior first-match rules produce a conflicting policy within suffix scope
- amazonaws.com (PROXY): CONFLICT — line 511: Prior first-match rules produce a conflicting policy within suffix scope
- baidu.com (DIRECT): CONFLICT — line 233: Prior first-match rules produce a conflicting policy within suffix scope
- biliapi.com (DIRECT): CONFLICT — line 98: Prior first-match rules produce a conflicting policy within suffix scope
- biliapi.net (DIRECT): CONFLICT — line 96: Prior first-match rules produce a conflicting policy within suffix scope
- bilibili.com (DIRECT): CONFLICT — line 308: Prior first-match rules produce a conflicting policy within suffix scope
- bilivideo.com (DIRECT): CONFLICT — line 439: Prior first-match rules produce a conflicting policy within suffix scope
- cdninstagram.com (PROXY): CONDITIONAL_POTENTIAL — line 51: Prior compound rule contains a matching domain operand; other operands are not evaluated
- cmbchina.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- dianping.com (DIRECT): CONFLICT — line 395: Prior first-match rules produce a conflicting policy within suffix scope
- ggpht.com (PROXY): CONDITIONAL_POTENTIAL — line 30: Prior compound rule contains a matching domain operand; other operands are not evaluated
- googleapis.cn (PROXY): CONDITIONAL_POTENTIAL — line 34: Prior compound rule contains a matching domain operand; other operands are not evaluated
- googleapis.com (PROXY): CONDITIONAL_POTENTIAL — line 35: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gstatic.cn (PROXY): CONDITIONAL_POTENTIAL — line 38: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gstatic.com (PROXY): CONDITIONAL_POTENTIAL — line 39: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gvt1.com (PROXY): CONDITIONAL_POTENTIAL — line 40: Prior compound rule contains a matching domain operand; other operands are not evaluated
- hdslb.com (DIRECT): CONFLICT — line 68: Prior first-match rules produce a conflicting policy within suffix scope
- hitv.com (DIRECT): CONFLICT — line 63: Prior first-match rules produce a conflicting policy within suffix scope
- hockeyapp.net (PROXY): CONFLICT — line 244: Prior first-match rules produce a conflicting policy within suffix scope
- instagram.com (PROXY): CONDITIONAL_POTENTIAL — line 50: Prior compound rule contains a matching domain operand; other operands are not evaluated
- iqiyi.com (DIRECT): CONFLICT — line 264: Prior first-match rules produce a conflicting policy within suffix scope
- jd.com (DIRECT): CONFLICT — line 162: Prior first-match rules produce a conflicting policy within suffix scope
- kuaishou.com (DIRECT): CONFLICT — line 282: Prior first-match rules produce a conflicting policy within suffix scope
- meituan.com (DIRECT): CONFLICT — line 265: Prior first-match rules produce a conflicting policy within suffix scope
- meituan.net (DIRECT): CONFLICT — line 97: Prior first-match rules produce a conflicting policy within suffix scope
- pinduoduo.com (DIRECT): CONFLICT — line 443: Prior first-match rules produce a conflicting policy within suffix scope
- qq.com (DIRECT): CONFLICT — line 136: Prior first-match rules produce a conflicting policy within suffix scope
- reddit.com (PROXY): CONFLICT — line 67: Prior first-match rules produce a conflicting policy within suffix scope
- sf-express.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- sina.com (DIRECT): CONFLICT — line 214: Prior first-match rules produce a conflicting policy within suffix scope
- sina.com.cn (DIRECT): CONFLICT — line 266: Prior first-match rules produce a conflicting policy within suffix scope
- taobao.com (DIRECT): CONFLICT — line 391: Prior first-match rules produce a conflicting policy within suffix scope
- tencent-cloud.net (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- tenpay.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- toutiao.com (DIRECT): CONFLICT — line 267: Prior first-match rules produce a conflicting policy within suffix scope
- twimg.com (PROXY): CONDITIONAL_POTENTIAL — line 42: Prior compound rule contains a matching domain operand; other operands are not evaluated
- wechat.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- weibo.com (DIRECT): CONFLICT — line 480: Prior first-match rules produce a conflicting policy within suffix scope
- weixin.com (DIRECT): ALREADY_COVERED — line None: Existing General skip-proxy entry
- x.com (PROXY): CONDITIONAL_POTENTIAL — line 45: Prior compound rule contains a matching domain operand; other operands are not evaluated
- xhscdn.com (DIRECT): CONFLICT — line 434: Prior first-match rules produce a conflicting policy within suffix scope
- xiaohongshu.com (DIRECT): CONFLICT — line 451: Prior first-match rules produce a conflicting policy within suffix scope
- ykimg.com (DIRECT): CONFLICT — line 195: Prior first-match rules produce a conflicting policy within suffix scope
- youku.com (DIRECT): CONFLICT — line 497: Prior first-match rules produce a conflicting policy within suffix scope
- youtu.be (PROXY): CONDITIONAL_POTENTIAL — line 46: Prior compound rule contains a matching domain operand; other operands are not evaluated
- youtube-nocookie.com (PROXY): CONDITIONAL_POTENTIAL — line 47: Prior compound rule contains a matching domain operand; other operands are not evaluated
- youtube.com (PROXY): CONDITIONAL_POTENTIAL — line 48: Prior compound rule contains a matching domain operand; other operands are not evaluated
- ytimg.com (PROXY): CONDITIONAL_POTENTIAL — line 52: Prior compound rule contains a matching domain operand; other operands are not evaluated
- zhihu.com (DIRECT): CONFLICT — line 366: Prior first-match rules produce a conflicting policy within suffix scope

## Errors

- None

Read-only report. No configuration or rule-set references were changed.
