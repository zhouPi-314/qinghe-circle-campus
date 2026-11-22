# 青禾流转未来扩展展望计划书（免费资源筛选版）

| 项目 | 内容 |
|---|---|
| 文档性质 | 未来展望与资源筛选，不是已批准需求 |
| 编制日期 | 2026-11-22 |
| 当前基线 | G5 已发布；业务代码不因本文自动扩张 |
| 费用原则 | 只保留免费试用或开源方向；不注册、不购买、不绑定支付方式 |
| 架构原则 | 低耦合、高内聚、模块化；外部服务一律通过适配器和端口隔离 |
| 批准边界 | 任何新产品范围、数据库、接口、运维依赖或付费动作都由用户另行批准 |

## 1. 目的与判断原则

本计划从 AI 星码博客中筛选与“校园物品流转与绿色回收平台”后续能力相符的资源，但博客只作为线索，不作为最终事实来源。任何候选进入开发前，都必须回到服务官网、服务条款、隐私政策和运行测试重新核实。

“免费”只表示当前标价为零，不代表没有以下成本：

- 账号与续期维护成本。
- 服务中断、迁移和数据导出的成本。
- 免费额度触发后的降级或付费风险。
- 邮件信誉、域名信誉和第三方安全拦截风险。
- 学生个人信息、管理员操作记录和投诉内容的合规风险。

本项目继续坚持以下边界：

- 不以免费工具替代高校授权、学生名单核验和公益物资线下验收。
- 不因某个免费服务支持某功能，就把它直接写进已批准范围。
- 不让学生个人资料进入无关的第三方统计、推送或 AI 服务。
- 真实支付、公开募捐、公益资金代收、实时聊天和真实物流仍需单独合规评估。

## 2. 资源分级

| 级别 | 含义 | 处理方式 |
|---|---|---|
| A | 免费能力与当前架构相容，可作为受控试验 | 先写设计、Mock 和验收条件，再由用户批准 |
| B | 可用于个人运维或临时验证，但不能承载核心业务 | 只做小规模 PoC，不进入主链路 |
| C | 与当前架构、隐私边界或免费承诺不符 | 不采用 |

## 3. 分阶段路线图

### P0：发布后稳定期（0–2 周）

目标：不再引入新的业务范围，只补齐生产运行可见性和入口安全。

| 事项 | 免费资源 | 处理建议 | 验收条件 |
|---|---|---|---|
| WAF 状态收口 | Cloudflare Free；DigitalPlat `qinghecircle.dpdns.org` | 已完成主域、兼容域、WAF、源站密钥和默认入口封锁；后续只做回归与续期 | 两个域名健康检查、扫描路径阻断、正常注册流程均通过 |
| 外站可用性监控 | Uptime Kuma；Cloudflare 监控类开源项目 | 先由外部定时探测 `/health` 与登录页；没有独立免费主机时只用现成平台监控，不自建第二套生产系统 | 故障能在约定时间提醒具体负责人 |
| 对外联系地址 | Cloudflare Email Routing | 已启用 `contact@qinghecircle.dpdns.org`；仅作收件转发 | 收信成功、MX/SPF/DKIM 正常、目标邮箱有效 |
| 免费域名续期台账 | DigitalPlat Dashboard | 记录到期日 2027-11-22、120 天免费续期窗口、账号 MFA、备用恢复方式 | 至少两人可取得恢复资料，不能只依赖一台设备 |

### P1：低成本产品增强（1–3 个月）

#### P1.1 通知中心与邮件适配器

现状：项目已有站内状态页面、审计和安全事件，但不应直接耦合某个邮件或推送供应商。

建议接口：

```text
NotificationPort.send(event)
  - in_app
  - email
  - operational_push

NotificationProvider
  - validate()
  - send()
  - provider_message_id()
  - health()
```

第一版约束：

- 业务服务只创建通知领域对象，不直接调用 SMTP、REST API 或 Bark。
- 默认使用内存或数据库 outbox；发送失败可重试，不能阻塞物品交接事务。
- 邮件内容不包含手机号、完整学号、交接码、验证码或争议隐私正文。
- 用户必须主动选择是否接收普通通知；关键安全通知另行评估。
- 任何邮件供应商都通过 adapter 替换，数据库不保存供应商内部 ID 作为主键。

候选：

- Polpo Mail Free：10 个邮箱/域名、1 GB/箱、IMAP/SMTP、无信用卡；当前拒绝本项目使用的二级域名，保留作主域场景备选。
- Amelu Free：1 个域名、官方当前表格显示 10 个邮箱、IMAP/SMTP、无信用卡。
- Cloudflare Email Routing：当前已用于 `contact@qinghecircle.dpdns.org` 收件转发；不适合作为任意收件人的免费事务邮件通道。

#### P1.2 图片预处理与存储成本控制

现状：物品图片和头像已支持 JPEG、PNG、WebP，生产存储使用 R2。后续可先做浏览器端尺寸限制和压缩，再把处理后的文件交给现有存储适配器。

候选：

- Squoosh：Google 开源图片优化工具，可参考其压缩与尺寸策略。
- 博客部署教程：[Squoosh 零成本部署说明](https://aixmb.com/754.html)。

建议接口：

```text
MediaProcessor.prepare(upload_stream, profile) -> PreparedMedia
  - normalized_mime
  - width
  - height
  - bytes
  - content_sha256
```

第一版只做本地压缩、尺寸上限、格式白名单和文件签名复核，不把原始学生图片上传到第三方压缩网站。引入任何服务端图像库前需重新审计依赖、CPU 限额和 Vercel 冷启动成本。

#### P1.3 外部可用性与证书监控

候选：

- Uptime Kuma：MIT License，支持 HTTP、DNS、证书和通知渠道。
- Cloudflare 免费监控项目：适合有独立 VPS 和服务器指标的场景。

判断：

- Uptime Kuma 为 B 级，需独立主机；在没有稳定运行位置时不得部署到生产应用同机。
- 当前应用运行在 Vercel 无长期本地磁盘的 Serverless 环境，`CF-Server-Monitor` 这类服务器面板不适用于当前主架构。
- 外部监控只保存服务状态，不采集学生业务数据。

### P2：条件成熟的增强（3–6 个月）

#### P2.1 管理员运维推送

候选：

- Bark：面向 iPhone 的 HTTP 推送，适合运维告警。
- Gotify： Android 自托管推送。

适用限制：

- 仅作为平台管理员的运维通知，不作为学生业务通知。
- 告警内容只包含服务名、错误类别和时间，不包含学生手机号、物品详情或完整错误堆栈。
- 需要撤权、轮换 token、失败重试和审计。
- 需要确认具体管理员设备平台，不能同时维护 Bark 与 Gotify 两套。

#### P2.2 表单、短链接与联系渠道

DigitalPlat 或其他博客资源提供表单、短链接和邮件转发。它们可以帮助公示联系入口，但不能替代：

- 站内 CSRF 与权限校验。
- 学生身份核验。
- 公益物资线下签收。
- 争议和投诉的审计闭环。

若未来采用，一律作为外围服务，不接入核心流转事务。

#### P2.3 公开内容与附件能力

博客中的 PDF、Office、压缩包工具和文件存储项目适合个人站点，但本项目目前只接受图片。若未来允许 PDF 或 Office 附件，必须新增：

- MIME、文件签名和解压炸弹防护。
- 恶意文件扫描供应商。
- 内容审核与版权投诉流程。
- 存储配额、保留期限和删除审计。

Cloudflare Free WAF 不能承担文件恶意内容扫描，不能只凭“已接 WAF”开放危险附件。

## 4. 资源候选总表

| 资源 | 博客来源 | 官方入口 | 级别 | 建议 |
|---|---|---|---|---|
| DigitalPlat FreeDomain | [文章](https://aixmb.com/680.html) | [官网](https://domain.digitalplat.org/) | A（已采用） | `qinghecircle.dpdns.org`；2027-11-22 到期，按 120 天窗口续期 |
| Polpo Mail | [文章](https://aixmb.com/1318.html) | [免费方案](https://polpomail.com/pricing) | B | 免费方案可用，但当前拒绝本项目子域名；不绕过限制 |
| Amelu | [文章](https://aixmb.com/1213.html) | [官网](https://amelu.org/) | A | Polpo 的替换备选 |
| Cloudflare Email Routing | 无直接同题博客 | [官方](https://developers.cloudflare.com/email-service/) | A | 免费收件和转发；不发任意收件人事务邮件 |
| Squoosh | [文章](https://aixmb.com/754.html) | [GitHub](https://github.com/GoogleChromeLabs/squoosh) | A | 参考或封装浏览器端压缩，不新建公开上传站 |
| Uptime Kuma | [文章](https://aixmb.com/1019.html) | [GitHub](https://github.com/louislam/uptime-kuma) | B | 有独立主机再做外站探测 |
| CF-Server-Monitor | [文章](https://aixmb.com/788.html) | [GitHub](https://github.com/huilang-me/CF-Server-Monitor) | B | 当前 Vercel/Neon 架构不适用 |
| Bark | [文章](https://aixmb.com/1026.html) | [官网](https://bark.day.app/) | B | 只用于管理员运维告警 |
| Gotify | [文章](https://aixmb.com/1033.html) | 需在开发前复核仓库 | B | 与 Bark 二选一，不并行维护 |
| KataBump 免费容器 | [文章](https://aixmb.com/609.html) | 需在开发前复核条款 | C | 308 MB、716 MB、每 4 天续期，不适合生产 |
| 免费 PHP/WordPress 主机 | [分类](https://aixmb.com/category/free-resources) | 各服务官网 | C | 不支持当前 Flask + PostgreSQL 主架构 |
| Cloudflare 临时邮箱开源项目 | [文章](https://aixmb.com/1084.html) | 需在开发前复核仓库 | C | 不用于域名注册、管理员、恢复或学生验证 |
| EdgeChat 等即时聊天部署 | [搜索页](https://aixmb.com/?s=Cloudflare) | 需在开发前复核仓库 | C | 实时聊天明确超出当前范围 |

## 5. 需要保留的架构接缝

未来扩展不得直接侵入现有业务 service：

| 接缝 | 所属层 | 规则 |
|---|---|---|
| `NotificationPort` | 通知 | 业务只发布领域事件；供应商实现可替换 |
| `MediaProcessor` | 文件 | 接收输入流，返回受控输出；不把第三方 URL 写进模型 |
| `ObservabilityProbe` | 运维 | 只读取公开健康页，不访问学生数据 |
| `ContactChannel` | 公示 | 只存配置引用，不硬编码个人邮箱 |
| `EdgeTrustPolicy` | 安全 | 继续要求源站密钥后才能信任 Cloudflare 客户端 IP |

所有适配器都应：

1. 有 Fake/Mock 实现，单元测试不访问外网。
2. 有超时、重试、速率限制和错误分类。
3. 不把密钥写入代码、日志、测试快照或 Markdown。
4. 有退出方案和数据导出方案。
5. 将第三方服务故障映射为领域错误，不泄露供应商原始敏感信息。

## 6. 不应进入当前路线图的项

| 能力 | 判断 | 原因 |
|---|---|---|
| 用随机免费域名冒充高校官方入口 | 禁止 | 可能构成误导；高校域名和身份数据须有授权 |
| 用临时邮箱接收学生验证或管理员恢复邮件 | 禁止 | 不具备可信身份、长期可恢复性和隐私保障 |
| 把公益项目改成真实公开募捐 | 暂不进入 | 涉及资质、资金托管、审计和法律责任 |
| 接入真实支付和退款 | 暂不进入 | 当前是模拟支付；真实支付需要单独合规设计 |
| 使用免费地图、骑手或物流 API 替代线下交接 | 暂不进入 | 当前明确排除地图导航和真实物流 |
| 开放实时聊天、音视频或直播 | 暂不进入 | 内容审核、未成年人保护和运维成本高 |
| 用无资质 AI 自动审核学生内容或定价 | 暂不进入 | 误判、偏见、隐私和申诉机制不成熟 |
| 为省成本把主应用迁到 4 天续期的容器 | 不采用 | 免费额度与续期机制不适合生产可靠性 |

## 7. 试验清单与退出条件

### E1：邮件联系地址

- 输入：一个已绑定的自定义域名。
- 操作：当前联系地址已使用 Cloudflare Email Routing；若未来需要完整双向信发，再评估 Polpo 主域方案或 Amelu，并先做独立端口与回退设计。
- 通过：自有邮箱收信、发信、垃圾邮件检查、DNS 健康检查正常。
- 退出：删除 MX/TXT，不删除网站 A/CNAME；邮件可导出。
- 时间估算：1–2 小时。

### E2：邮件通知适配器

- 输入：站内通知事件和邮件 adapter。
- 操作：测试成功、超时、退信、重试、关闭通知。
- 通过：业务事务不被邮件故障阻塞；日志无 PII。
- 退出：关闭 provider 开关，保留站内通知。
- 时间估算：1–2 个开发日。

### E3：图片预处理

- 输入：现有 JPEG、PNG、WebP 样本。
- 操作：限制尺寸并压缩，再执行服务端文件签名校验。
- 通过：质量可接受、R2 体积下降、失败明确提示。
- 退出：停止调用 processor，回退原上传路径。
- 时间估算：0.5–1 个开发日。

### E4：外部可用性监控

- 输入：公开 `/health` 和登录页。
- 操作：每分钟或每五分钟探测，连续失败后通知。
- 通过：误报率可接受，告警不含业务数据。
- 退出：移除监控，不影响应用。
- 时间估算：0.5 小时。

### E5：管理员运维推送

- 输入：单个管理员设备和一个最小权限 token。
- 操作：只发送服务状态和错误类别。
- 通过：可撤权、可轮换、可审计、无学生 PII。
- 退出：删除 token 和推送配置。
- 时间估算：0.5–1 个开发日。

## 8. 推荐优先级

1. 先完成当前 Cloudflare WAF 与 DigitalPlat 域名状态收口，保留主域和兼容域回归。
2. 再做外部可用性监控，优先发现入口和证书失效。
3. 有明确对外联系需求时，再启用免费域名邮箱。
4. 需要应用发邮件时，先实现 `NotificationPort` 和站内 outbox，再接供应商。
5. 图片处理优先在浏览器端完成，避免无必要的服务端 CPU 和第三方图片上传。
6. 即时聊天、真实募资、真实支付、地图物流和 AI 审核不因“资源免费”进入范围。

## 9. 批准与记录

本文不构成功能批准。后续若选择任一 A 级资源进入开发，应先：

1. 明确用户需求和成功指标。
2. 复核当前免费额度、条款、隐私、数据位置和退出机制。
3. 写模块接缝、数据库影响和失败降级方案。
4. 记录新的决策条目。
5. 在独立分支和 Preview 环境验证。

## 10. 主要来源

- [AI 星码博客](https://aixmb.com/)
- [AI 星码免费资源栏目](https://aixmb.com/category/free-resources)
- [DigitalPlat 官网](https://domain.digitalplat.org/)
- [Polpo Mail 免费方案](https://polpomail.com/pricing)
- [Amelu 官网](https://amelu.org/)
- [Cloudflare Email Service](https://developers.cloudflare.com/email-service/)
- [Uptime Kuma](https://github.com/louislam/uptime-kuma)
- [Squoosh](https://github.com/GoogleChromeLabs/squoosh)
