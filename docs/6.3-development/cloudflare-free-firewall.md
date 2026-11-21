# Cloudflare Free 防火墙接入评估

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 当前入口 | `https://qinghe-circle-campus.vercel.app` |
| 当前主机 | Vercel |
| 结论 | 当前 vercel.app 无法直接接入 Cloudflare WAF；需要自有域名 |
| 推荐顺序 | 应用层防护先行，自定义域名接入后启用 Cloudflare 代理 |

## 1. 当前限制

Cloudflare WAF 只保护添加到用户 Cloudflare 账户并开启 DNS 代理的域名。`vercel.app` 由 Vercel 控制，不属于本项目自有域名，因此不能为 `qinghe-campus.vercel.app` 添加 Cloudflare WAF、Bot Fight Mode 或 Rate Limiting。

同时，即使以后启用自定义域名，默认 `*.vercel.app` 地址可能仍可访问。Cloudflare 是边缘防护层，不是唯一安全边界；应用层的高校权限、验证码、IP HMAC 频控和黑名单必须继续存在。

## 2. 接入前提

1. 一个用户可管理的域名。
2. 域名 DNS 托管到 Cloudflare。
3. 在 Vercel Project Settings → Domains 添加该域名。
4. 在 Cloudflare DNS 添加 Vercel 要求的 CNAME/A 记录并开启 Proxy（橙色云）。
5. Cloudflare SSL/TLS 使用 Full (strict)，避免降级到 Flexible。
6. 确认 Vercel 域名验证、证书和重定向均正常。

域名购买属于付费和账户操作，必须在用户明确确认价格和续费责任后执行。

## 3. 免费能力与限制

| 能力 | Free 可用性 | 本项目用途 |
|---|---|---|
| Free Managed Ruleset | 所有套餐可用 | 拦截常见高危 Web 漏洞与扫描 |
| Bot Fight Mode | Free 可用 | 挑战自动化机器人 |
| Rate Limiting Rule | Free 提供基础规则额度 | 限制 `/auth/register/*` 请求 |
| Turnstile | 有免费额度 | 可作为图形验证码增强，非首版必需 |
| WAF 事件日志 | Free 能力有限 | 依赖应用 `security_events` 补充审计 |

WAF 不扫描上传文件内部的恶意代码。当前只允许 JPEG/PNG/WebP 和文件签名校验；若未来允许 Office、PDF、压缩包或可执行附件，需另接恶意文件扫描服务。

## 4. 项目代码改动

### 4.1 可信客户端 IP

- 新增 `TRUST_CLOUDFLARE_IP_HEADER` 配置，默认 `false`。
- 自定义域名经 Cloudflare 代理后设为 `true`。
- 开启时读取 `CF-Connecting-IP`；关闭时使用 Vercel 提供的请求地址。
- 只保存 IP 的 HMAC，不保存完整 IP。
- 禁止直接信任公网客户端自行提交的 `CF-Connecting-IP`。

### 4.2 应用层注册防火墙

- 同一 IP 在滚动 10 分钟内第 9 次验证码请求时，阻止继续请求 15 分钟。
- 同一 IP 24 小时内再次触发 2 次后升级为 24 小时封禁。
- 永久封禁仅由平台管理员复核执行。
- 自动封禁只作用于 `/auth/register/*`，避免校园共享 NAT 影响全站。
- 所有临时封禁、升级、解除和误报标记写入审计。

### 4.3 平台运维页

- `/admin/operations` 只对平台管理员开放。
- 展示应用/数据库健康、SMS Provider 配置、发送/失败统计、安全事件和临时封禁。
- 展示脱敏错误日志和业务审计；不展示手机号、验证码、Cookie、Secret 或完整请求体。

## 5. Cloudflare 规则建议

### Managed Rules

- 启用 Free Managed Ruleset。
- 初始动作使用托管默认，不在没有样本的情况下全局 Block。

### Bot Fight Mode

- 启用 Bot Fight Mode。
- 观察登录、注册、健康检查和静态资源是否被误挑战。

### Rate Limiting

Free 只有有限规则，优先保护注册：

```text
匹配路径：/auth/register/*
统计维度：IP
阈值：10 分钟 10 次（略宽于应用层第 9 次阻断）
动作：Managed Challenge
```

应用层仍是最终业务限制；Cloudflare 只负责尽早卸载明显洪峰。

## 6. 上线验证

1. `qinghe-campus.vercel.app` 和应用层防护仍可用。
2. 自定义域名通过 Cloudflare 代理，证书为 Full (strict)。
3. 直接访问 Vercel 默认域名仍受应用层频率限制。
4. 连续第 9 次短信请求被应用阻断，产生 `sms_ip_threshold`。
5. Cloudflare 挑战/阻断不导致健康检查、登录、静态资源和正常注册失效。
6. 平台运维页可查看安全事件、错误和封禁处置结果。
7. 解除封禁和误报标记有审计记录。

## 7. 获取与配置步骤

1. 已有域名：登录 Cloudflare → Add a site → 选择 Free → 按提示替换 Nameserver。
2. 没有域名：使用 Cloudflare Registrar 或合规域名注册商购买；此步骤涉及付款，需要用户确认。
3. 在 Vercel 添加域名并完成验证。
4. Cloudflare DNS 按 Vercel 要求添加记录并开启代理。
5. Cloudflare → Security → WAF 开启 Free Managed Ruleset。
6. Cloudflare → Bots 开启 Bot Fight Mode。
7. Cloudflare → Security → WAF Rate Limiting 创建注册路径规则。
8. 先部署 Preview 自定义域名验证，再切换 Production。

## 8. 官方参考

- Cloudflare Managed Rules：<https://developers.cloudflare.com/waf/managed-rules/>
- Bot Fight Mode：<https://developers.cloudflare.com/bots/get-started/bot-fight-mode/>
- Rate Limiting Rules：<https://developers.cloudflare.com/waf/rate-limiting-rules/>
- Cloudflare HTTP Headers：<https://developers.cloudflare.com/fundamentals/reference/http-headers/>
- Vercel Proxy Guide：<https://vercel.com/kb/guide/can-i-use-a-proxy-on-top-of-my-vercel-deployment>
