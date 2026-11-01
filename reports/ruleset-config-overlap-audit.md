# RULE-SET / user-config overlap audit

- Authority: read-only shadowrocket/ss.conf
- First RULE-SET line: 653
- Earlier active rules: 623
- Ledger candidates: 935
- Result: PASS

## Status counts

- CONDITIONAL_POTENTIAL: 15
- CONFLICT: 1
- NOT_COVERED_BY_PRIOR_DOMAIN_RULES: 919

## Findings

- 1e100.net (PROXY): CONDITIONAL_POTENTIAL — line 28: Prior compound rule contains a matching domain operand; other operands are not evaluated
- cdninstagram.com (PROXY): CONDITIONAL_POTENTIAL — line 51: Prior compound rule contains a matching domain operand; other operands are not evaluated
- ggpht.com (PROXY): CONDITIONAL_POTENTIAL — line 30: Prior compound rule contains a matching domain operand; other operands are not evaluated
- googleapis.cn (PROXY): CONDITIONAL_POTENTIAL — line 34: Prior compound rule contains a matching domain operand; other operands are not evaluated
- googleapis.com (PROXY): CONDITIONAL_POTENTIAL — line 35: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gstatic.cn (PROXY): CONDITIONAL_POTENTIAL — line 38: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gstatic.com (PROXY): CONDITIONAL_POTENTIAL — line 39: Prior compound rule contains a matching domain operand; other operands are not evaluated
- gvt1.com (PROXY): CONDITIONAL_POTENTIAL — line 40: Prior compound rule contains a matching domain operand; other operands are not evaluated
- hockeyapp.net (PROXY): CONFLICT — line 244: Prior first-match exact/suffix domain rule
- instagram.com (PROXY): CONDITIONAL_POTENTIAL — line 50: Prior compound rule contains a matching domain operand; other operands are not evaluated
- twimg.com (PROXY): CONDITIONAL_POTENTIAL — line 42: Prior compound rule contains a matching domain operand; other operands are not evaluated
- x.com (PROXY): CONDITIONAL_POTENTIAL — line 45: Prior compound rule contains a matching domain operand; other operands are not evaluated
- youtu.be (PROXY): CONDITIONAL_POTENTIAL — line 46: Prior compound rule contains a matching domain operand; other operands are not evaluated
- youtube-nocookie.com (PROXY): CONDITIONAL_POTENTIAL — line 47: Prior compound rule contains a matching domain operand; other operands are not evaluated
- youtube.com (PROXY): CONDITIONAL_POTENTIAL — line 48: Prior compound rule contains a matching domain operand; other operands are not evaluated
- ytimg.com (PROXY): CONDITIONAL_POTENTIAL — line 52: Prior compound rule contains a matching domain operand; other operands are not evaluated

## Errors

- None

Read-only report. No configuration or rule-set references were changed.
