# G5 发布候选证据

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-22 |
| 分支 | `workerbuddy/g5-university-admin-sms` |
| 基线 | `e042b61` |
| 当前状态 | G5-A、G5-B、G5-C 已合并、迁移并部署到 Production（2026-11-22） |
| 数据库 | 31 张表（原 27 张 + 注册验证 1 张 + 运维安全 3 张） |

## 1. 校级管理员

- 校级管理员只使用自己的 `university_id`。
- 停用或不存在的学校拒绝继续管理。
- 可查看本校概览、校区、站点、账号、名单、内容审核、争议和审计。
- 可创建本校公益管理员，停用本校学生或公益管理员；停用公益管理员时同事务结束站点授权。
- 不能创建高校、管理平台管理员或跨校读写。
- 组织页和账号名单页均通过真实 HTTP 表单测试。

## 2. 注册验证

- 图形验证码由 Pillow 生成 PNG，2 分钟有效、一次消费，仅保存 HMAC。
- 生产短信 Provider 为阿里云号码认证短信认证。
- 阿里云使用 `SendSmsVerifyCode` / `CheckSmsVerifyCode`，系统生成验证码，不保存明文。
- 短信 60 秒重发、300 秒有效、最多 5 次失败、状态 pending/sent/ignored/consumed/failed/expired。
- 名单不匹配、手机号不匹配和已注册状态均返回统一文案。
- Mock 码只在非 Production 环境显示；Production 配置 Mock 会启动失败。

真实阿里云 smoke：

- `SendSmsVerifyCode` 返回 `OK`，`BizId` 存在。
- 维护者测试手机收到验证码。
- 错误码真实返回 `isv.ValidateFail`，Provider 已修正为“验证码错误”而不是服务故障。
- 测试手机号和 AccessKey 只保存在桌面 ACL 受限的 TXT 与 Git 忽略的 `.env.local`。

## 3. 运维与安全中心

- 新增 `security_events`、`security_blocks`、`application_events`。
- 同 IP 10 分钟第 9 次注册短信请求触发 15 分钟临时封禁。
- PostgreSQL advisory lock 按 IP HMAC 串行化并发检查；活动封禁另有唯一索引。
- 平台运维页展示运行状况、短信成功/失败、攻击分类、应用错误和封禁处置。
- 封禁解除与误报标记写业务审计。
- 10 分钟阈值可能影响共享校园 NAT，因此只阻断注册短信并保留人工解除路径。

## 4. Cloudflare

- 应用支持 `CF-Connecting-IP`，但只有 `X-Qinghe-Origin-Secret` 与 `CLOUDFLARE_ORIGIN_SECRET` 常量时间匹配时才信任。
- 直接访问 `vercel.app` 无法伪造 Header 绕过 IP 频控。
- 当前 `vercel.app` 不能直接启用 Cloudflare WAF；要接入必须使用自有域名并代理到 Vercel。
- 域名接入仍待用户提供域名或批准购买，因此 Cloudflare 实际规则尚未在 Production 启用。

## 5. 测试与迁移

最终结果：

- `pytest`：286 passed。
- `ruff check app tests`：通过。
- `pip-audit -r requirements.txt`：升级 Flask 3.1.3、pytest 9.0.3 后无已知漏洞。
- 两项添加式迁移在 27 表旧基线上回放后得到 31 表。

G5 功能集成后的阶段性结果：

- 校级管理员与治理：全量 234 passed。
- 注册验证持久化：全量 244 passed。
- Captcha/PNVS Provider：全量 257 passed。
- 注册验证服务：全量 267 passed。
- 注册页面：全量 272 passed。
- 运维安全：全量 278 passed。
- 最终回归：286 passed。

迁移：

- `sql/migrations/20261121_g5_registration_verification.sql`
- `sql/migrations/20261121_g5_security_operations.sql`
- 两项均为添加式；Production 迁移前为 27 张表、141 所高校、161 条校区和 1 个账号，迁移后为 31 张表。
- Vercel 使用 Sensitive 环境变量，禁止本地拉取生产连接串；迁移通过一次性随机令牌入口在 Vercel 运行时内完成，入口和令牌随后删除。

## 6. 安全与文档检查

- 当前 `.env.local` 中的密钥、生产管理员密码、短信测试手机号和数据库连接串未出现在 Git 跟踪文件或 Git 历史中。
- 7 份课程 Word 由 Markdown 重新生成，结构检查均为 0 个高、中、低问题。
- 7 份 Word 经 Microsoft Word 导出 PDF 并逐页检查，共 73 页，无裁切、重叠、表格断裂或缺失图片。
- Word 全文复核未发现“校级管理员预留”“管理功能暂未开放”“真实短信不可用”等旧表述。

## 7. 未完成

- Cloudflare 自有域名/DNS/WAF 控制台配置。
- 未单独创建 Neon 克隆库；迁移前已核对生产表数和核心行数，迁移 SQL 为添加式且已在本地 PostgreSQL 18 回归。

## 8. 界面证据

- `g5-register.png`：注册图形验证码、短信验证码、60 秒提示。
- `g5-school-admin.png`：校级管理员本校概览。
- `g5-operations.png`：恶意攻击分类、临时封禁、运行状况和应用错误。
