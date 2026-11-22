# DigitalPlat + Cloudflare Free 零成本部署记录

| 项目 | 内容 |
|---|---|
| 初始核查日期 | 2026-11-22 19:36（Asia/Shanghai） |
| 执行完成日期 | 2026-11-22（Asia/Shanghai） |
| 核查方式 | Microsoft Edge A 方案实访博客、服务官网与 Cloudflare/Vercel 官方文档；公开 DNS 查询；只读 HTTP 冒烟 |
| 文档状态 | 已按用户批准执行；研究部分保留为决策依据 |
| 结论 | DigitalPlat `qinghecircle.dpdns.org` 已以 0 元注册并委派到 Cloudflare；Cloudflare Free WAF、请求头转换、Email Routing 已配置；Vercel Production 将只接受白名单 Host 与源站密钥 |
| 代码影响 | 新增 Production Host/源站密钥入口校验；不改数据库、业务接口或页面范围 |
| 费用边界 | 不注册、不购买、不确认任何付费项；任一页面出现付款、信用卡或非 0 元金额即停止 |

## 1. 结论先行

用户随后批准改用 DigitalPlat 免费域名，并授权提交入口架构修改。执行结果：

- `qinghecircle.dpdns.org` 已注册为 Active，到期日为 2027-11-22，到期前 120 天可免费续费。
- DigitalPlat 公告中的 `.us.kg`、`.xx.kg` 限制已核对，本次使用 `dpdns.org`，未注册暂停后缀。
- Cloudflare 分配的权威 NS 为 `dave.ns.cloudflare.com`、`love.ns.cloudflare.com`。
- Vercel 已完成 `_vercel` 验证；两条 A 记录 `64.29.17.1`、`216.198.79.1` 均为 Proxied。
- Universal SSL 正常，SSL/TLS 模式为 Full (strict)，最低 TLS 为 1.2。
- 主域名及兼容域名 `qinghecircle.de5.net` 各自配置 Request Header Transform Rule，向源站注入同一随机密钥；密钥不写入本文档。

免费域名仍存在续期、平台政策、公共后缀和声誉风险，因此保留 `qinghecircle.de5.net` 作为兼容入口，不把它描述为永久或企业级 SLA。

## 2. WAF 对域名的硬性要求

以下条件缺一不可：

1. 域名或子域名能委派自定义权威 NS，而不只是提供 A、CNAME、TXT 记录编辑。
2. 该域名作为独立 Zone 添加到 Cloudflare，并处于 Full setup、已激活状态。
3. 网站记录经过 Cloudflare Proxy，即 DNS 记录显示为 Proxied（橙色云）。
4. Cloudflare 能为该 Zone 签发可被浏览器信任的证书。
5. Vercel 项目已接受该自定义域名，Cloudflare 到 Vercel 的证书链有效。
6. 免费额度、免费续期和免费 DNS 委派在注册时仍成立。
7. 账号启用可靠 MFA，恢复邮箱与密码不依赖同一服务。

“能添加 CNAME 到 Cloudflare Pages”不等于“能把整个域名交给 Cloudflare”。很多博客所称的“支持 Cloudflare”实际只是在其自己的 DNS 面板里填写 CNAME；这种域名不能单独创建 Cloudflare Zone，也不能获得本项目的 Zone 级 WAF、Bot Fight Mode 与速率限制。

## 3. 当前线上只读验证

| 检查 | 观察结果 | 判断 |
|---|---|---|
| 自定义域名页面 | Edge 加载站点成功 | HTTPS 和页面路由可用 |
| `/health` | HTTP 200；`Server: cloudflare`；存在 `CF-RAY` | 请求经过 Cloudflare |
| `/.env` | HTTP 403；`Server: cloudflare` | 自定义阻断规则生效 |
| HSTS | `strict-transport-security: max-age=63072000` | HSTS 响应存在 |
| NS | `dave.ns.cloudflare.com`、`love.ns.cloudflare.com` | Zone 由 Cloudflare 托管 |
| A | `104.21...`、`172.67...` 系列 Cloudflare Anycast 地址 | DNS 记录已代理 |
| Universal SSL | Active，Google DNS 可见 Cloudflare 证书链 | 免费证书正常 |
| 请求头转换 | 两个 Zone 各有 1 条 Active 规则 | 源站密钥只由 Cloudflare 注入 |
| `vercel.app` 默认入口 | 不经本项目 Cloudflare Zone | 需由应用层 Host/密钥守卫阻止 |

## 4. 免费域名候选评估

| 来源 | 免费与 NS 能力 | 本次判断 |
|---|---|---|
| 当前 `qinghecircle.de5.net` | 已托管到 Cloudflare；保留为兼容入口 | **备用入口** |
| DigitalPlat FreeDomain | 官方流程支持外部权威 NS；本次 `dpdns.org` 注册页为 0 元 | **已采用**：`qinghecircle.dpdns.org` |
| Stackryze Domains | 博客称 `.indevs.in`、`.sryze.cc` 支持 Cloudflare，但官网进入 Cloudflare 安全验证，未能独立复核当前条款 | **不列为可执行方案** |
| GNAME `.eu.cc` | 博客称可领 3 个免费名额；当前官网公开价格为 `$1.88/年`，续费 `$1.88/年`，优惠券页未见 `.eu.cc` 免费券 | **排除，不符合“必须免费”** |
| HapDNS | 博客明确写明当时不支持托管到 Cloudflare | **排除，无法获得 Zone 级 WAF** |
| isroot.in | 博客明确写明当时不支持托管到 Cloudflare | **排除，无法获得 Zone 级 WAF** |
| Nya.je / Devs.Surf / LovieMe / DEVS.LI | 主要是自有 DNS 编辑或记录代管，文章亦提示不能完全托管到 Cloudflare | **排除** |

### 4.1 DigitalPlat 为什么可以作为备选

DigitalPlat 官方学习指南将职责明确分成：

```text
DigitalPlat：登记名称并保存外部权威 NS
Cloudflare：承载独立 Zone、配置 A/CNAME/MX/TXT 等记录
Vercel：运行网站并接受自定义域名
```

其 FAQ 当前说明每个账号默认只有 1 个免费域名，且是否免费、可用后缀、名额和续期规则都可能变化，必须以 Dashboard 当前显示为准。官网当前宣传“Free registration available”，但部分命名空间或额外名额可以收费，所以不能把首页宣传直接当成任意后缀永久免费。

### 4.2 后缀选择

Public Suffix List 当前包含：

- `dpdns.org`
- `us.kg`
- `xx.kg`
- `qzz.io`

当前列表未发现 `qd.je`。Cloudflare Universal SSL 的免费证书覆盖规则与可注册域名层级有关，因此即使某个免费后缀暂时可注册，也优先选择已进入 Public Suffix List 的后缀。备选排序建议为：

1. 结账明确显示 0 元的 `*.dpdns.org`
2. 结账明确显示 0 元的 `*.us.kg`
3. 结账明确显示 0 元的 `*.xx.kg`
4. 结账明确显示 0 元的 `*.qzz.io`
5. 不以 `qd.je` 作为主入口，除非届时 PSL、证书和续期均已重新核实

Public Suffix List 也可能变化，以上不是永久保证。

## 5. 免费域名邮箱评估

域名邮箱不是 Cloudflare WAF 的前置条件。若要对外提供项目联系地址，可在 WAF 稳定后再做，避免把两个外部故障点同时引入。

| 服务 | 当前免费能力 | 是否适合本项目 |
|---|---|---|
| Polpo Mail | €0 永久计划；每域名最多 10 个邮箱；每箱 1 GB；无信用卡；支持 IMAP、SMTP、SPF、DKIM、DMARC、MTA-STS | 当前服务端明确拒绝 `qinghecircle.dpdns.org` 等子域名，要求注册主域 `dpdns.org`；未绕过校验 |
| Amelu | €0 永久计划；1 个域名；官方当前表格显示每域名最多 10 个邮箱；无需信用卡；支持 IMAP/SMTP/POP3、转发和 Catch-all | **备用**；欧盟托管，免费出站约 150 封/日/域名 |
| Cloudflare Email Routing | 免费接收并转发到已验证地址 | **已采用**：`contact@qinghecircle.dpdns.org`；任意收件人的事务邮件发送不是 Free 能力 |
| TinkMail 限时免费商业版 | 博客描述为限时活动，不是稳定的永久免费承诺 | **不作为依赖** |

最低风险做法是先用项目现有的受控个人邮箱作为域名注册、Cloudflare、Vercel 和恢复邮箱，再按需增加 `contact@自定义域名`。注册、付款、云平台管理员账号不要共用同一个免费域名邮箱作为唯一恢复方式。

Cloudflare 官方当前说明：

- Email Routing 在 Workers Free 和 Paid 均可用。
- 发往账号内已验证目标地址的邮件可在 Free 使用。
- 面向任意收件人的事务邮件发送需要 Workers Paid。

因此，当前版本不应把“免费 Cloudflare 邮件发送”写成已具备的应用通知能力。

## 6. 推荐决策

### 已执行：DigitalPlat + Cloudflare Email Routing

执行结果：

1. `qinghecircle.dpdns.org` 注册、NS 委派、Vercel 绑定和 Cloudflare Universal SSL 均已完成。
2. Cloudflare Free Managed Ruleset、1 条自定义扫描路径阻断、Bot Fight Mode 和 1 条注册接口速率限制已启用。
3. Vercel Production 已配置 `TRUST_CLOUDFLARE_IP_HEADER`、`CLOUDFLARE_ORIGIN_SECRET`、`PUBLIC_ALLOWED_HOSTS`。
4. `contact@qinghecircle.dpdns.org` 的 MX、SPF、DKIM 已通过，路由状态为 Active。
5. `qinghecircle.de5.net` 保留为兼容入口，并配置同样的请求头转换规则。
6. `vercel.app` 默认入口由应用层 Host 白名单和共享密钥封锁，不能仅依赖 Cloudflare。

## 7. Cloudflare Free 规则边界

当前官方资料显示：

- Free Managed Ruleset 在所有套餐可用，主要覆盖高影响、广泛利用的漏洞。
- Free 计划对请求体的 Managed Rules 检查上限为 1 MB。
- Bot Fight Mode 免费，但不可由 WAF 自定义规则精细排除，可能挑战 API、移动客户端或监控流量。
- Free 速率限制只有 1 条规则，统计周期和缓解时间均为 10 秒，计数特征为 IP。
- Free 自定义规则上限为 5 条，不支持正则。

这纠正了现有文档中“Cloudflare Free 按 10 分钟窗口限制注册路径”的旧表述：10 分钟第 9 次阻断属于应用层规则，不是当前 Cloudflare Free 边缘规则能直接复刻的配置。

推荐只把唯一一条 Free 边缘速率限制用于高成本或高风险入口，例如：

```text
路径：/auth/register
计数：IP
窗口：10 秒
阈值：10 次
动作：Block
阻断持续时间：10 秒
```

最终业务频控仍以应用层的 10 分钟、24 小时和人工复核规则为准。

## 8. WAF 上线验收

每个验收项都必须分别记录：

| 验收项 | 通过条件 |
|---|---|
| Zone 激活 | 公共 DNS 查询返回 Cloudflare NS |
| HTTPS | 浏览器无证书警告，证书主机名匹配 |
| 代理 | 响应含 `Server: cloudflare` 与 `CF-RAY` |
| 正常业务 | `/health` 200；登录、注册、静态资源和关键页面可用 |
| 已知扫描路径 | `/.env` 等路径被阻断或挑战，未到达 Flask 业务路由 |
| Bot 规则 | 正常浏览器、注册流程和健康检查未被误伤 |
| 源 IP | 只有 Cloudflare 源站密钥校验通过后才采用 `CF-Connecting-IP` |
| 直连边界 | 明确记录 `vercel.app` 默认入口仍可绕过 WAF，不能宣称全站 WAF 覆盖 |
| 成本 | Cloudflare 套餐为 Free；登录、DNS、证书页面未出现待付款项 |

## 9. 风险、隐性成本与纠偏

### 9.1 免费不等于无成本

- 时间成本：注册、NS 传播、证书签发、DNS 回滚和邮件 DNS 验证需要人工值守。
- 运维成本：免费域名需要关注到期、续期窗口、策略变化和账号 MFA。
- 声誉成本：公共免费子域名可能被邮件接收方、浏览器或安全供应商降低信任。
- 业务连续性：DigitalPlat 条款明确不承诺 SLA，并提示不要把它作为唯一身份或关键生产入口。

### 9.2 代理后链路风险

Vercel 官方提示：外部反向代理会降低 Vercel 对客户端信号和安全事件的可见性；代理只是额外入口，不会自动阻断 Vercel 默认部署地址。Cloudflare 到 Vercel 应使用 Full (strict)，并保留 ACME/域名验证路径不被 WAF 或缓存阻断。

### 9.3 不能夸大的安全结论

- WAF 不检查上传图片内部的恶意载荷。
- WAF 不能替代学号名单、角色权限、CSRF、验证码、频控、审计和争议处置。
- 自定义域名受 WAF 保护，不代表 `vercel.app` 默认入口也受保护。
- 任何“全站仅能经过 WAF”的目标都需要额外限制源站入口，属于架构变更，需另行批准。

## 10. 已纠正的旧前提

1. **旧前提：DNShe 的 DNSSEC 阻塞是最终状态。**
   `qinghecircle.de5.net` 后来已恢复 HTTPS；本项目随后按用户批准迁移主入口到 DigitalPlat `dpdns.org`，并保留旧入口兼容。

2. **旧前提：Cloudflare Free 可按 10 分钟窗口做边缘速率限制。**
   当前官方 Free 参数是 1 条规则、10 秒计数、10 秒缓解；长窗口规则由应用层承担。

3. **旧前提：`.eu.cc` 当前仍可无条件免费。**
   博客文章已过时；GNAME 官网当前公开价为 `$1.88/年`，优惠券页未显示该免费活动，不能执行。

4. **旧前提：所有“支持 Cloudflare”的免费域名都能开 WAF。**
   只有支持权威 NS 委派并把完整域名作为 Zone 接入的才满足；仅能配置 CNAME 的不满足。

5. **旧前提：Polpo Mail 可直接绑定任意免费子域名。**
   实际注册时服务端要求主域，明确拒绝 `qinghecircle.dpdns.org`；没有绕过限制。当前使用 Cloudflare Email Routing 作为免费收件转发替代。

## 11. 执行边界与未执行项

- 已创建 DigitalPlat 免费域名与 Cloudflare Free Zone，未启用付费计划。
- 未购买 Vercel Pro、Cloudflare 付费 WAF、域名或邮箱套餐。
- 未创建 GNAME、Amelu 或 Polpo Mail 付费项；Polpo Mail 因子域名限制未完成。
- 未改数据库结构、业务规则或页面范围。
- 已按用户批准增加 Production Host 白名单与源站密钥守卫。
- `qinghecircle.dpdns.org` 为主入口；`qinghecircle.de5.net` 保留为兼容入口。

## 12. 后续维护项

1. 在 2027-08-25 前后开始检查 DigitalPlat 免费续期入口，并分别在到期前 90、60、30、7 天复核。
2. 关注 DigitalPlat 公告和后缀政策；新注册前再次确认目标后缀免费且未暂停。
3. 轮换 `CLOUDFLARE_ORIGIN_SECRET` 时，必须同时更新 Vercel 与两个 Cloudflare Zone 的请求头规则，再执行公网验收。
4. 监控 `contact@qinghecircle.dpdns.org` 转发目标是否仍有效、MX/SPF/DKIM 是否漂移。
5. 定期验证主域、兼容域、默认 Vercel 域名、最新 deployment URL、健康检查和注册流程。

## 13. 来源

### 博客

- [AI 星码首页](https://aixmb.com/)
- [DigitalPlat 免费域名、短链接、邮箱转发](https://aixmb.com/680.html)
- [Stackryze Domains 免费域名](https://aixmb.com/616.html)
- [GNAME `.eu.cc` 免费域名教程](https://aixmb.com/871.html)
- [HapDNS 免费域名](https://aixmb.com/974.html)
- [Nya.je 免费 DDNS](https://aixmb.com/1098.html)
- [LovieMe 免费子域名](https://aixmb.com/1181.html)
- [Devs.Surf 免费子域名](https://aixmb.com/1205.html)
- [Amelu 域名邮箱](https://aixmb.com/1213.html)
- [isroot.in 免费域名](https://aixmb.com/1295.html)
- [Polpo Mail 域名邮箱](https://aixmb.com/1318.html)

### 服务与官方规范

- [DigitalPlat 官网](https://domain.digitalplat.org/)
- [DigitalPlat FreeDomain 仓库](https://github.com/DigitalPlatDev/FreeDomain)
- [DigitalPlat NS 委派说明](https://github.com/DigitalPlatDev/FreeDomain/blob/main/documents/tutorial/platform/1.3-connect-nameservers.md)
- [DigitalPlat 注册说明](https://github.com/DigitalPlatDev/FreeDomain/blob/main/documents/tutorial/platform/1.2-domain-registration.md)
- [DigitalPlat 续期说明](https://github.com/DigitalPlatDev/FreeDomain/blob/main/documents/tutorial/platform/1.4-status-and-renewal.md)
- [DigitalPlat FAQ](https://github.com/DigitalPlatDev/FreeDomain/blob/main/documents/domains/faq.md)
- [Public Suffix List](https://publicsuffix.org/list/public_suffix_list.dat)
- [Cloudflare Free Managed Ruleset](https://developers.cloudflare.com/waf/managed-rules/)
- [Cloudflare Rate Limiting Rules](https://developers.cloudflare.com/waf/rate-limiting-rules/)
- [Cloudflare Custom Rules](https://developers.cloudflare.com/waf/custom-rules/)
- [Cloudflare Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/)
- [Cloudflare Bot Fight Mode](https://developers.cloudflare.com/bots/get-started/bot-fight-mode/)
- [Cloudflare Email Service](https://developers.cloudflare.com/email-service/)
- [Vercel 与 Cloudflare 等反向代理](https://vercel.com/kb/guide/can-i-use-a-proxy-on-top-of-my-vercel-deployment)
- [Vercel 自定义域名](https://vercel.com/docs/domains/working-with-domains/add-a-domain)
- [Polpo Mail 免费方案](https://polpomail.com/pricing)
- [Amelu 免费方案](https://amelu.org/)
- [GNAME 域名价格](https://www.gname.net/domain)
- [GNAME 优惠券页](https://www.gname.net/coupons)
