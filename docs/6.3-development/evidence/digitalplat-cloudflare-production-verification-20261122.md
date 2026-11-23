# DigitalPlat 与 Cloudflare Free 生产验证

| 项目 | 内容 |
|---|---|
| 验证日期 | 2026-11-22 |
| 主入口 | `https://qinghecircle.dpdns.org` |
| 兼容入口 | `https://qinghecircle.de5.net` |
| Vercel 代码提交 | `3c7c050` |
| 文档验证提交 | `08a2253` |
| 数据库 | PostgreSQL 18，31 张表 |
| 自动化回归 | pytest 298 项通过；`app` 与 `tests` 的 Ruff 检查通过 |

## 公网验收

| 检查 | 结果 |
|---|---|
| 主域 `/health` | 200，`Server: cloudflare`，存在 `CF-RAY` |
| 兼容域 `/health` | 200，经过 Cloudflare |
| `/`、`/auth/login`、`/auth/register` | 200，正常页面未被 WAF 误伤 |
| `/.env` | Cloudflare 403 |
| 默认 `qinghe-circle-campus.vercel.app/health` | 应用 404 |
| 最新 deployment URL | Vercel Deployment Protection 拦截，不触达 Flask |
| 注册速率限制 | 同 IP 连续请求第 11、12 次返回 429；10 秒窗口结束后恢复 200 |

## Cloudflare

- DigitalPlat 域名状态 Active，有效期至 2027-11-22，到期前 120 天可免费续期。
- 两个自定义域名均使用 Cloudflare Proxied DNS 和 Full (strict)。
- Free Managed Ruleset、扫描路径阻断和 Bot Fight Mode 已启用。
- 注册速率限制条件为 `URI Path contains /auth/register`，10 秒内 10 次，Block 10 秒。
- 两个 Zone 各自通过 Request Header Transform Rule 注入同一源站密钥；密钥不进入仓库。
- 普通首页不强制显示 Managed Challenge；WAF 命中扫描特征时直接返回 403，Bot Fight Mode 和注册限速按各自规则处理。

## 免费收件转发

- 对外地址为 `contact@qinghecircle.dpdns.org`。
- Cloudflare Email Routing 路由状态 Active。
- MX、SPF 和 DKIM 查询通过。
- 该能力只负责收件转发，不是任意收件人的免费事务邮件发送服务。

## 已知边界

- 仓库 `tools/` 目录仍有 16 个历史 Ruff 问题，与本次部署无关，未在发布提交中修改。
- Cloudflare Free 只有一条速率限制规则和 10 秒窗口，长窗口业务频控仍由应用层执行。
- 免费域名、证书和邮件路由均依赖第三方服务连续性，续期和策略变化需要持续检查。
