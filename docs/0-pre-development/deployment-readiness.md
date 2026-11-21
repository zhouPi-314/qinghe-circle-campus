# 青禾流转部署前技术检查清单（公开版）

检查日期：2026-11-19
公开发布脱敏：2026-11-21

## 1. 结论

云基础设施已经达到可部署状态，但应用本身尚不具备部署条件。

当前状态：

- Neon PostgreSQL：可用，已完成真实连接测试。
- Cloudflare R2：可用，已完成上传和公网读取测试。
- Vercel 项目：已创建，已连接 GitHub，已配置环境变量。
- GitHub 仓库：已连接 Vercel，但仓库当前没有应用代码。
- Flask 应用：尚无入口、依赖文件、数据库模型或页面。

因此，当前是：

> 基础设施就绪，应用代码未就绪，暂不能进行有意义的公网部署。

## 2. 已完成的云资源

### Neon

| 项目 | 状态 |
|---|---|
| Project | `qinghe-circle-campus` |
| Project ID | `<NEON_PROJECT_ID>` |
| Region | AWS Asia Pacific 1 (Singapore) |
| Plan | Free |
| Branch | production |
| Branch ID | `<NEON_BRANCH_ID>` |
| Database | `neondb` |
| PostgreSQL | 18.7 |
| Connection pooling | 已使用 pooled connection string |
| 实际查询 | 已通过 |

### Cloudflare R2

| 项目 | 状态 |
|---|---|
| Bucket | `qinghe-circle-campus` |
| Cloudflare Account ID | `<CLOUDFLARE_ACCOUNT_ID>` |
| Location | Asia-Pacific |
| Public Development URL | 已启用 |
| Public Base URL | `<R2_PUBLIC_BASE_URL>` |
| API Token | 已创建，账户级 |
| Token 权限 | Object Read & Write |
| Token 范围 | 仅当前 Bucket |
| Token 有效期 | 6 个月 |
| S3 上传 | 已通过 |
| 公网读取 | 已通过 |
| 测试对象删除 | 已通过 |
| Bucket 残留测试文件 | 无 |

R2 使用 Base URL：

```text
https://<PUBLIC_DEVELOPMENT_URL>.r2.dev
```

对象完整访问地址为：

```text
https://<PUBLIC_DEVELOPMENT_URL>.r2.dev/<OBJECT_KEY>
```

### Vercel

| 项目 | 状态 |
|---|---|
| Team | `<VERCEL_TEAM>` |
| Plan | Hobby |
| Project | `qinghe-circle-campus` |
| Project ID | `<VERCEL_PROJECT_ID>` |
| Framework Preset | Flask |
| Root Directory | `.` |
| Git Repository | `zhouPi-314/qinghe-circle-campus` |
| Production Branch | `main` |
| GitHub Connection | 已连接 |
| Function Region | Singapore (`sin1`) |
| Production Deployment | 尚无 |

## 3. Vercel 环境变量

以下变量已经写入 Production 和 Preview：

| 变量 | 类型 |
|---|---|
| `DATABASE_URL` | Secret |
| `SECRET_KEY` | Secret |
| `R2_ACCESS_KEY_ID` | Secret |
| `R2_SECRET_ACCESS_KEY` | Secret |
| `CLOUDFLARE_ACCOUNT_ID` | Config |
| `R2_BUCKET_NAME` | Config |
| `R2_ENDPOINT` | Config |
| `R2_PUBLIC_BASE_URL` | Config |

本地 `.env.local` 还包含 Vercel Link 自动生成的短生命周期 OIDC Token；不属于 Flask 业务变量。

## 4. 已验证的连接

### Neon

- Flask/SQLAlchemy 将使用 `postgresql+psycopg://`。
- 已从本地使用 `psycopg` 成功连接。
- 已执行 `SELECT current_database(), current_user, version()`。

### R2

- 已使用 `boto3` 和 S3-compatible API 成功上传对象。
- 已通过 Public Development URL 成功读取同一个对象。
- 已成功删除测试对象。
- 当前不需要 CORS，因为首版计划由 Vercel Flask 服务端上传，不由浏览器直接上传。

## 5. 安全状态

- 真实密钥只存放在 `.env.local`。
- `.env.local` 已加入 `.gitignore`。
- `.env.example` 仅包含占位符。
- `.vercel/` 已加入 `.gitignore`。
- 临时 Vercel CLI Token `qinghe-circle-campus-cli` 已撤销删除。
- 本地 `VERCEL_TOKEN` 已从 `.env.local` 移除。
- R2 Secret Access Key 未出现在项目代码或 Markdown 文档中。
- Vercel Authenticator App 2FA 已验证并处于 Active / Enrolled 状态。

## 6. 尚未完成的部署前置条件

### 必须完成

- [ ] 创建 Flask 应用入口。
- [ ] 创建 `requirements.txt` 或 `pyproject.toml`。
- [ ] 创建 Vercel Python/WSGI 适配入口。
- [ ] 创建 PostgreSQL 模型和初始化 SQL。
- [ ] 在 Neon 中创建业务表。
- [ ] 创建至少一个可访问页面。
- [ ] 验证静态文件、Jinja2 模板和登录页可在 Vercel 运行。
- [x] 将 Vercel Function 区域设置为 `sin1`，与 Neon 新加坡区域靠近。
- [ ] 推送最小可运行版本到 GitHub `main`。
- [ ] 完成首次 Preview/Production 部署并检查构建日志。
- [ ] 在公网环境验证数据库读写。
- [ ] 在公网环境验证 R2 图片上传和公网读取。

### 建议完成

- [ ] 使用真实但脱敏的演示数据初始化数据库。
- [ ] 添加数据库备份/导出策略；Neon Free 不包含完整自动备份。
- [ ] 为 R2 设置对象大小和 MIME 白名单。
- [ ] 为 Flask 设置安全 Cookie、CSRF 防护和上传限制。
- [x] 完成 Vercel Authenticator App 2FA 绑定。
- [ ] 检查 Cloudflare 和 Neon 是否也需要启用独立 2FA。
- [ ] 使用 Vercel Preview 环境测试后续版本，再合并到 production。
- [ ] 对公网 URL 做移动端和桌面端响应式测试。
- [ ] 在 README 中写明环境变量、初始化步骤和已知限制。

## 7. 建议的首次部署验收

首次部署完成后，至少确认：

1. 首页返回 HTTP 200。
2. Flask 能读取 Neon 数据库。
3. 登录或测试账号可以访问受保护页面。
4. 未登录访问受保护页面会被拒绝。
5. 图片可上传到 R2，并可公开读取。
6. 不同高校用户不能看到其他学校的业务数据。
7. 生产环境不出现调试模式、堆栈泄露或明文密钥。
8. Vercel 日志中无数据库连接和 R2 鉴权错误。

## 8. 当前唯一阻塞

不是云平台阻塞，而是应用工程尚未开始：

```text
GitHub repository is empty
→ no Flask entrypoint
→ no database schema
→ no deployable artifact
→ no meaningful production URL
```

