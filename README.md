# Shadowrocket 项目

本仓库统一维护 Shadowrocket 主配置、规则集、域名采集与审核自动化，以及可选脚本/模块。

## 主配置

- 主配置文件：[`shadowrocket/ss.conf`](shadowrocket/ss.conf)
- 订阅地址：`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

主配置是独立维护对象。迁移脚本和模块时，不自动启用它们，也不自动改动主配置中的 DNS、规则或 MITM 设置。

## 项目目录

- `.github/workflows/`：GitHub Actions 工作流
- `shadowrocket/ss.conf`：主配置
- `rulesets/`：DIRECT、PROXY、REJECT 规则集及清单
- `sources/`：域名来源、审核账本、策略与基线
- `scripts/`：域名采集、筛选、审核、规则集构建和配置验证
- `data/`、`reports/`、`dist/`：采集数据、审计报告和构建产物
- `modules/adblock/`：社交与搜索广告处理脚本
- `modules/maasea/`：Maasea 相关 YouTube 脚本、模块和许可证

## 可选模块的使用边界

迁移到仓库不代表已启用或已验证其设备端效果：

- `modules/adblock/Social_Adblock.js`：独立脚本，尚未接入主配置。
- `modules/maasea/youtube-ads.sgmodule`：独立模块。其响应体脚本针对 `youtubei.googleapis.com`，模块说明明确指出需要对该主机进行 HTTPS 解密；本项目主配置不因此启用 MITM。
- `modules/maasea/youtube_request_local.js`：代码中包含对 `https://init-stream.maasea.workers.dev/` 的外部 Worker 依赖。使用前应单独审查其网络请求与数据处理。
- `modules/maasea/youtube_response.js`：YouTube 响应处理脚本。

这些模块不会因文件迁移而自动进入 `ss.conf`。在确认兼容性、隐私边界和设备端效果之前，不应直接启用。

## 许可证与来源

`modules/maasea/LICENSE-APACHE-2.0-Maasea` 随 Maasea 相关文件一并保留。使用、修改或再分发相关上游代码时，应阅读并遵守该许可证及各文件原有版权声明。
