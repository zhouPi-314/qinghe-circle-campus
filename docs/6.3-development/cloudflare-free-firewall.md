# DigitalPlat + Cloudflare Free 防火墙接入记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-22 |
| 当前入口 | `https://qinghecircle.dpdns.org` |
| 兼容入口 | `https://qinghecircle.de5.net` |
| 当前主机 | Vercel |
| 域名来源 | DigitalPlat FreeDomain，`qinghecircle.dpdns.org`，免费注册，Active |
| 域名期限 | 2026-11-22 至 2027-11-22；到期前 120 天可免费续费 |
| 套餐与成本 | Cloudflare Free（$0）；未开通付费域名、WAF、邮箱或 Vercel Pro |
| 当前状态 | Cloudflare Zone Active；Vercel 域名验证通过；Universal SSL 正常；Full (strict)；Managed Free Ruleset、Bot Fight Mode、扫描路径阻断和注册接口限流已启用；两个自定义域名的请求头转换规则均 Active |
| 入口边界 | Cloudflare 只保护两个自定义域名；`vercel.app` 直连由应用层 Host 白名单和源站密钥封锁 |

## 1. 当前限制

Cloudflare WAF 只保护添加到用户 Cloudflare 账户并开启 DNS 代理的域名。`vercel.app` 由 Vercel 控制，不属于本项目自有域名，因此不能为 `qinghe-circle-campus.vercel.app` 添加 Cloudflare WAF、Bot Fight Mode 或 Rate Limiting。

Cloudflare 是边缘防护层，不是唯一安全边界。应用层的高校权限、验证码、IP HMAC 频控和黑名单必须继续存在。

默认 `*.vercel.app` 地址不接受 Vercel 账号内的 WAF 规则。当前项目在 Production 增加 Host 白名单与 `X-Qinghe-Origin-Secret` 双重校验：只有两个批准域名且请求头匹配时进入应用，其他 Production Host 统一返回 404。Cloudflare 为两个域名分别注入该请求头，应用侧用常量时间比较验证。

## 2. 为什么正常首页不显示“真人验证”

Cloudflare WAF 是规则匹配型防护，不是“所有访客自动弹验证码”的开关。当前配置中：

- Free Managed Ruleset 只对命中托管规则的请求采取托管动作；
- 扫描路径自定义规则只阻断 `.env`、`.git`、常见后台探测路径和高风险方法；
- Bot Fight Mode 主要处理被识别为自动化的流量，不保证每个普通浏览器访客看到挑战页；
- 注册接口速率限制只在阈值触发后 Block，不向正常 GET 页面注入挑战；
- `/health`、首页、登录和注册页面被明确保持可访问，避免健康检查、搜索和正常用户被误伤。

因此，首页对普通浏览器返回正常页面是预期行为，不代表请求没有经过 Cloudflare。验收应同时检查响应中的 `Server: cloudflare` / `CF-RAY`，并用扫描路径验证边缘阻断。

如果确实要在普通首页强制显示托管挑战，需要另建 WAF 自定义规则，例如匹配 `http.request.uri.path eq "/"` 后执行 **Managed Challenge**。应至少排除 `/health`，并先确认 API、静态资源、登录回跳和移动端体验不受影响。该做法会降低可访问性，不应仅为了“看到验证码”而全站启用。

Cloudflare 的 Managed Challenge 页面由 Cloudflare 托管，不能嵌入应用登录页。若需要在登录页右侧显示验证组件，应使用 Turnstile：

1. 在 Cloudflare Dashboard 创建 Turnstile Widget，允许 `qinghecircle.dpdns.org` 和兼容域名。
2. 将公开 Site Key 与私密 Secret Key 分别写入本地 `.env.local` 和 Vercel Production Secrets。
3. 两项同时存在时，登录页自动显示官方组件；应用向 Siteverify 校验 token，失败则拒绝登录。
4. 两项均未配置时，应用使用自身图片验证码，不影响本地开发和紧急回退。
5. 只配置其中一项会快速失败，避免误以为安全验证已经启用。

## 3. 接入前提

1. 一个用户可管理的域名。
2. 域名 DNS 托管到 Cloudflare。
3. 在 Vercel Project Settings → Domains 添加该域名。
4. 在 Cloudflare DNS 添加 Vercel 要求的 CNAME/A 记录并开启 Proxy（橙色云）。
5. Cloudflare SSL/TLS 使用 Full (strict)，避免降级到 Flexible。
6. 确认 Vercel 域名验证、证书和重定向均正常。

域名购买属于付费和账户操作，必须在用户明确确认价格和续费责任后执行。

## 4. 免费能力与限制

| 能力 | Free 可用性 | 本项目用途 |
|---|---|---|
| Free Managed Ruleset | 所有套餐可用 | 拦截常见高危 Web 漏洞与扫描 |
| Bot Fight Mode | Free 可用 | 挑战自动化机器人 |
| Rate Limiting Rule | Free 提供基础规则额度 | 限制 `/auth/register` 请求 |
| Turnstile | 有免费额度 | 登录页右侧安全验证；未配置时回退为自托管图片验证码 |
| WAF 事件日志 | Free 能力有限 | 依赖应用 `security_events` 补充审计 |

WAF 不扫描上传文件内部的恶意代码。当前只允许 JPEG/PNG/WebP 和文件签名校验；若未来允许 Office、PDF、压缩包或可执行附件，需另接恶意文件扫描服务。

## 5. 项目代码改动

### 5.1 可信客户端 IP

- 新增 `TRUST_CLOUDFLARE_IP_HEADER` 配置，默认 `false`。
- 新增 `CLOUDFLARE_ORIGIN_SECRET`，由 Cloudflare Request Header Transform 规则注入 `X-Qinghe-Origin-Secret`。
- 自定义域名经 Cloudflare 代理后设为 `true`。
- 只有共享源站密钥常量时间校验通过后，才读取 `CF-Connecting-IP`；否则使用 Vercel 提供的请求地址。
- 只保存 IP 的 HMAC，不保存完整 IP。
- 禁止直接信任公网客户端自行提交的 `CF-Connecting-IP`。

当前实现位于 `app/core/security_monitor.py:trusted_client_ip()`；只有环境变量显式为 true、源站密钥匹配且 Header 是合法 IP 时才采用，否则回退 `request.remote_addr`。这防止直接访问 vercel.app 时伪造 `CF-Connecting-IP`。

### 5.2 应用层注册防火墙

- 同一 IP 在滚动 10 分钟内第 9 次验证码请求时，阻止继续请求 15 分钟。
- 同一 IP 24 小时内再次触发 2 次后升级为 24 小时封禁。
- 永久封禁仅由平台管理员复核执行。
- 自动封禁只作用于 `/auth/register`，避免校园共享 NAT 影响全站。
- 所有临时封禁、升级、解除和误报标记写入审计。

### 5.3 平台运维页

- `/admin/operations` 只对平台管理员开放。
- 展示应用/数据库健康、SMS Provider 配置、发送/失败统计、安全事件和临时封禁。
- 展示脱敏错误日志和业务审计；不展示手机号、验证码、Cookie、Secret 或完整请求体。

## 6. Cloudflare 规则建议

当前已部署：

- Free Managed Ruleset：Cloudflare 标记为 `Always active`，规则集详情显示 42 条免费托管规则。
- 自定义规则 `Block common scanner paths and unsafe methods`：匹配 `.env`、`.git`、`.php`、`/actuator/`、`/server-status`、`/phpmyadmin` 以及 TRACE/TRACK/CONNECT，动作 `Block`。

### Managed Rules

- 启用 Free Managed Ruleset。
- 初始动作使用托管默认，不在没有样本的情况下全局 Block。

### Bot Fight Mode

- 启用 Bot Fight Mode。
- 观察登录、注册、健康检查和静态资源是否被误挑战。

### Rate Limiting

Free 只有一条基础速率限制规则，当前用于保护注册入口：

```text
匹配条件：URI Path contains /auth/register
统计维度：IP
窗口：10 秒
阈值：10 次
动作：Block
阻断持续时间：10 秒
```

应用层仍是最终业务限制；Cloudflare 只负责尽早卸载明显洪峰。应用层继续执行 60 秒重发间隔和 10 分钟内第 9 次触发临时封禁等长窗口策略。

## 7. 上线验证

2026-11-22 发布后实测：

| 验收项 | 结果 |
|---|---|
| 主域健康检查 | `https://qinghecircle.dpdns.org/health` 返回 200，`Server: cloudflare`，存在 `CF-RAY` |
| 兼容域健康检查 | `https://qinghecircle.de5.net/health` 返回 200 |
| 首页、登录、注册 GET | 均返回 200，未被 Bot Fight Mode 或 WAF 误伤 |
| 扫描路径 | `https://qinghecircle.dpdns.org/.env` 返回 Cloudflare 403 |
| 默认 Vercel 域名 | `https://qinghe-circle-campus.vercel.app/health` 返回应用 404 |
| Deployment URL | 仍由 Vercel Deployment Protection 登录页拦截，不触达 Flask |
| 注册速率限制 | 同 IP 连续请求第 11、12 次返回 Cloudflare 429；10 秒后恢复 200 |
| 自动化回归 | pytest 298 项通过；`app` 与 `tests` 的 Ruff 检查通过 |

应用层长窗口封禁、平台运维页和审计仍需按既有测试继续验收。

2026-11-23 补充复核：

| 检查 | 结果 |
|---|---|
| 首页 `GET /` | 302，响应含 `Server: cloudflare` 和 `CF-RAY` |
| 扫描器特征和 SQL 注入查询串 | Cloudflare 403 |
| `/.env` | Cloudflare 403 |
| DNS A 记录 | `172.67.221.25`、`104.21.70.73`，属于 Cloudflare 代理地址 |

本次复核没有看到挑战页，与当前“按规则阻断、普通流量放行”的配置一致。

## 8. 获取与配置步骤

1. 已有域名：登录 Cloudflare → Add a site → 选择 Free → 按提示替换 Nameserver。
2. 免费域名：按 DigitalPlat 当前免费名额选择后缀；避开暂停注册的 `.us.kg`、`.xx.kg`，本次使用 `.dpdns.org`。
3. 在 Vercel 添加域名并完成验证。
4. Cloudflare DNS 按 Vercel 要求添加记录并开启代理。
5. Cloudflare → Security → WAF 开启 Free Managed Ruleset。
6. Cloudflare → Bots 开启 Bot Fight Mode。
7. Cloudflare → Security → WAF Rate Limiting 创建注册路径规则。
8. 先部署 Preview 自定义域名验证，再切换 Production。

本次另配置免费 Cloudflare Email Routing：`contact@qinghecircle.dpdns.org` 转发至 Cloudflare 账号内已验证邮箱。该能力仅覆盖收件转发，不提供任意收件人的免费事务邮件发信。

## 9. 官方参考

- Cloudflare Managed Rules：<https://developers.cloudflare.com/waf/managed-rules/>
- Bot Fight Mode：<https://developers.cloudflare.com/bots/get-started/bot-fight-mode/>
- Rate Limiting Rules：<https://developers.cloudflare.com/waf/rate-limiting-rules/>
- Cloudflare HTTP Headers：<https://developers.cloudflare.com/fundamentals/reference/http-headers/>
- Vercel Proxy Guide：<https://vercel.com/kb/guide/can-i-use-a-proxy-on-top-of-my-vercel-deployment>
