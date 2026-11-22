# G5 校级管理员与注册短信验证设计提案

| 项目 | 内容 |
|---|---|
| 文档编号 | G5-DESIGN-001 |
| 日期 | 2026-11-21 |
| 状态 | 已实现并通过 G5-R 回归（D-054） |
| 范围 | G5-A 校级管理员；G5-B 注册图形验证码与阿里云短信认证；G5-C 平台运维与攻击治理 |
| 当前基线 | `main@260a99a` |
| 写入规则 | 设计阶段 Codex；获批后 WorkerBuddy 单写入实现；Codex 验收 |

## 1. 目标

将当前只能登录的校级管理员扩展为受高校边界约束的本校管理角色，并把学生注册从“名单匹配后直接建号”升级为“图形验证码 + 手机号验证码 + 名单匹配后建号”。

完成后：

- 校级管理员能处理本校日常管理，但不能创建高校、管理平台管理员或访问其他学校。
- 学生注册必须证明能接收名单预留手机号的验证码。
- 本地测试和 GitHub 复刻不依赖真实短信；生产环境使用阿里云短信认证服务。
- 平台管理员拥有统一的运行状况、安全攻击分类、错误和脱敏日志视图。
- Cloudflare Free 与应用层防火墙形成双层防护；受 vercel.app 域名限制时明确采用自定义域名方案。
- 原有平台管理员、公益管理员、学生业务与公网地址保持兼容。

## 2. 校级管理员范围

### 2.1 纳入

1. 本校概览：用户、校区、站点、物品、流转、公益项目数量。
2. 本校组织：新增/维护校区，新增/维护回收与公益站点。
3. 本校账号：创建公益管理员，启用/停用本校普通账号，分配公益管理员站点。
4. 本校名单：上传学生 CSV、查看导入批次与失败摘要。
5. 本校治理：审核物品并下架，查看和处理本校争议，查看本校审计。

### 2.2 不纳入

- 创建高校、修改高校代码、跨校维护组织。
- 创建或停用平台管理员、校级管理员。
- 修改自己的角色、高校归属或提升为平台管理员。
- 导出完整学生名单或手机号明文。
- 删除审计、争议、状态历史或业务记录。
- 真实短信余额充值、短信模板管理页面；这些仍在阿里云控制台完成。

### 2.3 权限模型

- `university_admin` 的有效高校只取会话用户快照的 `university_id`，不信任表单传入的高校 ID。
- 每次操作都重新确认所属高校存在且状态为 `active`；高校停用后，校级管理员只能看到停用说明，不能继续管理。
- 平台管理员保持全局能力；校级管理员只获得明确的“本校管理”能力。
- 路由守卫是入口校验，service 层再次校验角色和高校边界。
- 跨校对象统一返回无权限或 404，不泄露对象是否存在。
- 校级管理员不能访问平台管理员的全局账号、创建高校和跨校列表。

### 2.4 页面策略

复用现有 `/admin` 管理页面和 service，按角色收窄视图，不新建第二套平行后台：

- `/admin`：平台管理员为全局概览，校级管理员为本校概览。
- `/admin/organizations`：校级管理员只能新增校区、站点和站点授权。
- `/admin/users`：校级管理员只能查看本校账号并创建公益管理员。
- `/admin/student-imports`：校级管理员固定导入本校名单。
- `/admin/moderation`、`/admin/disputes`、`/admin/audit`：校级管理员只看到本校记录。

## 3. 注册验证码范围

### 3.1 注册流程

```text
填入学号、手机号、密码
  → 获取并输入图形验证码
  → 服务端匹配本校名单
  → 调用阿里云短信认证 `SendSmsVerifyCode`
  → 学生输入手机验证码并提交注册
  → 服务端调用 `CheckSmsVerifyCode`，锁定记录并校验手机号
  → 创建学生账号并原子消费验证码
```

### 3.2 参数

- 图形验证码：4 位大写字母和数字，2 分钟有效，只能使用一次。
- 手机验证码：6 位数字，由阿里云短信认证生成，5 分钟有效，60 秒后可重发，最多失败 5 次。
- 同一名单记录同时最多一条有效验证记录。
- 应用侧限制同一手机号 1 条/分钟、5 条/小时、10 条/天。
- 同一 IP 在任意滚动 10 分钟内第 9 次请求验证码时，临时禁止继续请求 15 分钟，并生成安全事件。
- 同一 IP 24 小时内再次触发 2 次后升级为 24 小时封禁；永久封禁必须由平台管理员复核后手工执行。
- 阿里云控制台继续启用发送频率限制、防盗刷监控和余量预警。

### 3.3 防枚举与防滥用

- 图形验证码错误明确提示；名单不匹配、手机号不匹配、重复注册统一返回“如果名单信息匹配，验证码将发送到预留手机号”。
- 短信接口不返回账号是否存在、名单姓名或校区。
- 图形验证码通过前不进入名单查询和短信发送。
- 先提交 `pending` 记录并占用重发额度，再调用服务商；并发请求不能穿透 60 秒冷却。
- 同一手机号与同一名单记录的发送必须间隔至少 60 秒，按钮显示倒计时且服务端再次校验。
- 名单不匹配的请求也写入 `status=ignored` 的脱敏尝试记录，只保存高校、手机号和学号的 HMAC、IP HMAC 与时间，用于同一维度的频控；不生成验证码，不调用短信。
- 日志、审计、错误页和测试报告不写完整手机号、短信验证码、AccessKey 或 Secret。
- 公开文本仍按现有 PII 规则过滤。

### 3.4 数据

新增 `registration_verification_requests`：

- `university_id`：学校边界。
- `student_registry_record_id`：绑定的名单记录；`ignored` 尝试允许为空。
- `student_no_hash`：用于未匹配请求频控的学号 HMAC。
- `phone_hash`：名单手机号 HMAC。
- `code_hash`、`salt`：Mock 验证码 HMAC 与随机盐；阿里云模式为空。
- `provider`：`mock` 或 `aliyun_pnvs`；`ignored` 尝试为空。
- `provider_message_id`：阿里云 `BizId`，不含手机号。
- `status`：`pending`、`sent`、`ignored`、`consumed`、`failed`、`expired`。
- `request_ip_hash`：用于频控，不保存 IP 明文。
- `failed_attempts`、`resend_after`、`expires_at`、`sent_at`、`consumed_at`。

注册最终提交时在同一个事务中校验并消费 `pending|sent` 记录，不设独立的 `verified` 状态。现有 `login_verification_codes.user_id` 非空且用途仅 `login`，注册前尚无 `user_id`，因此不复用该表。

## 4. 阿里云短信认证接口边界

当前阿里云账号为个人认证，普通短信服务没有资质和签名，无法完成签名实名报备。账号已开通“短信认证服务”，包含系统赠送签名和登录/注册模板，因此改用号码认证服务提供的短信认证能力。实际余量、签名和模板值只配置在本地与平台 Secret 中，不写入公开仓库。

依赖：

- `alibabacloud_dypnsapi20170525==2.0.0`
- `pillow==13.0.0`

Provider 接口：

```python
class SmsSender(Protocol):
    def send_register_code(self, phone: str, out_id: str) -> SmsSendResult: ...
    def verify_register_code(self, phone: str, code: str, out_id: str) -> bool: ...

@dataclass(frozen=True)
class SmsSendResult:
    provider: str
    message_id: str | None
```

实现：

- `MockSmsSender`：测试和本地开发使用，不访问网络。
- `AliyunPnvsSmsSender`：使用官方 V2 SDK、`SendSmsVerifyCode`、`CheckSmsVerifyCode` 和 RAM 用户 AccessKey。
- Mock 模式返回固定的合成验证码，由注册页明确标注“本地模拟验证码”；只有 `VERCEL_ENV != production` 且 `SMS_PROVIDER=mock` 时可显示。Production 配置为 Mock 时启动失败。
- 阿里云发送参数：`CodeLength=6`、`CodeType=1`、`Interval=60`、`ValidTime=300`、`DuplicatePolicy=1`、`ReturnVerifyCode=false`、`AutoRetry=1`。
- 赠送登录/注册模板变量固定为 `{"code":"##code##","min":"5"}`；不记录系统生成验证码。
- `OutId` 使用注册验证记录 UUID，不允许包含手机号或学号明文。

环境变量：

- `SMS_PROVIDER=mock|aliyun_pnvs`
- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
- `ALIYUN_PNVS_SIGN_NAME`
- `ALIYUN_PNVS_TEMPLATE_CODE`
- `ALIYUN_PNVS_REGION_ID`，默认 `cn-hangzhou`

生产环境 `SMS_PROVIDER=aliyun_pnvs` 但依赖配置缺失时启动失败，不能静默降级为 mock。真实凭据只放 `.env.local` 与 Vercel Secrets，不进入聊天、代码、Issue 或测试报告。

RAM 最小权限：`dypns:SendSmsVerifyCode`、`dypns:CheckSmsVerifyCode`。不授予普通短信管理、账号管理或其他云资源权限。

关于“联通 SDK 升级”：《号码认证标准版本升级公告》针对安卓、iOS、H5 客户端号码认证 SDK，要求客户端升级并下载最新版 SDK；本项目是服务端 Web 注册，不集成客户端取号或一键登录，因此不需要另下 Android/iOS/H5 SDK。若未来接入一键登录，再单独立项。

阿里云官方资料：

- 使用流程与审核：<https://help.aliyun.com/zh/sms/getting-started/get-started-with-sms>
- 短信认证操作指南：<https://help.aliyun.com/zh/pnvs/user-guide/sms-authentication-service>
- SendSmsVerifyCode：<https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode>
- CheckSmsVerifyCode：<https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-checksmsverifycode>
- 联通号码认证客户端 SDK 升级公告：<https://help.aliyun.com/zh/pnvs/product-overview/upgrade-phone-number-verification-service-sdk-standard-edition>

## 6. 平台运维与攻击治理

新增平台管理员专属 `/admin/operations`：

1. 运行状况：应用与数据库健康、SMS Provider 配置状态、最近 24 小时验证码发送量、失败量、临时封禁数和未关闭安全事件。
2. 恶意攻击：按 `sms_ip_threshold`、`captcha_failure_burst`、`registration_enumeration`、`blocked_ip_retry` 分类，记录严重度、事件次数、首次/最近时间和处置状态。
3. 报错与日志：展示脱敏的应用错误事件、业务审计和短信发送结果；支持时间、级别、分类筛选。
4. 封禁处置：平台管理员可将临时封禁升级、解除或标记误报；解除与升级必须写审计。

新增数据：

- `security_events`：攻击分类、严重度、IP HMAC、次数、状态、时间窗。
- `security_blocks`：IP HMAC、原因、开始/结束时间、状态、处置人。
- `application_events`：级别、事件码、请求标识、路由、摘要、结构化详情、时间和可选学校/用户。

安全规则：

- 共享校园 NAT 可能让多个正常学生呈现同一 IP，因此自动封禁只限制注册和短信端点，不封禁全站，并采用临时封禁而非永久拉黑。
- 平台管理员可以白名单或解除误报；永久封禁仅人工执行。
- 日志不记录手机号、验证码、Cookie、AccessKey、Secret、完整 IP 或完整请求体。
- 默认保留 30 天；清理任务失败不影响主业务。

## 7. Cloudflare Free 防火墙

Cloudflare 官方 Free Managed Ruleset 面向所有套餐；Free 套餐还提供 Bot Fight Mode 和一条基础 Rate Limiting 规则。计划启用：

- Free Managed Ruleset。
- Bot Fight Mode。
- 单条针对 `/auth/register/*` 的 IP 限速规则，阈值与 App 的“10 分钟 8 次”规则一致或略宽，避免先于应用误伤正常请求。

关键前提：`vercel.app` 主机名不能直接启用本项目 Cloudflare Zone 的 WAF。当前已使用 `qinghecircle.dpdns.org` 和兼容域名 `qinghecircle.de5.net` 作为 Cloudflare Proxied 入口；默认 `vercel.app` Production Host 由应用层白名单和源站密钥守卫返回 404，因此不能把它描述为受 Cloudflare WAF 保护。

在 Cloudflare 代理场景中，应用优先读取 `CF-Connecting-IP`；直接访问 Vercel 时回退到平台提供的可信转发头。若无法证明请求来自 Cloudflare，不能信任客户端自行提交的同名 Header。

Cloudflare WAF 能拦截常见 Web 攻击、恶意扫描和自动化机器人，但不等于文件杀毒软件。当前项目只允许 JPEG、PNG、WebP 图片并校验文件签名；若未来允许文档、压缩包或可执行附件，必须另接对象存储恶意文件扫描，不能把 WAF 宣称为病毒扫描器。

官方参考：

- Cloudflare Managed Rules：<https://developers.cloudflare.com/waf/managed-rules/>
- Bot Fight Mode：<https://developers.cloudflare.com/bots/get-started/bot-fight-mode/>
- Rate Limiting：<https://developers.cloudflare.com/waf/rate-limiting-rules/>
- Vercel 与 Cloudflare 代理：<https://vercel.com/kb/guide/can-i-use-a-proxy-on-top-of-my-vercel-deployment>

## 8. 非功能要求

- 添加式迁移：新表、必要唯一约束，不删除既有字段。
- 迁移失败时不部署新应用版本。
- 真实短信超时、服务商错误和额度不足不会创建学生账号。
- 服务商已返回成功但随后本地状态更新失败时，`pending` 记录仍可在有效期内参与注册；冷却期内不自动重发，防止重复计费。
- 平台管理员现有测试必须继续通过。
- 短信 provider 在测试中必须可替换，自动化测试不发送真实短信。
- 真实 smoke test 只向维护者控制的手机号发送，并记录阿里云 `BizId`，不记录验证码。
- 测试手机号只存本地 `.env.local` 的 `SMS_SMOKE_TEST_PHONE`，不写入 `.env.example`、文档、Issue、日志或 GitHub。
- 自动攻击分类必须保留误报处置路径；安全事件不替代公安或云厂商事件响应。

## 9. 需要用户确认

1. 上述校级管理员范围是否批准。
2. 是否批准“可以创建公益管理员、停用本校普通账号、处理本校争议”这三项校级权限。
3. 阿里云签名、模板和测试手机号由用户准备；凭据不通过聊天发送。
4. 是否提供自有域名并接入 Cloudflare 代理；若不提供，Cloudflare WAF 只能列为后续部署项。
