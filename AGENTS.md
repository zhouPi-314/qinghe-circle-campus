# 青禾流转项目开发规则

本文件是仓库的统一开发入口。修改代码、数据库、部署或公开文档前，先阅读本文件及它指向的规范。

## 当前状态

- 项目：青禾流转（Qinghe Circle Campus）
- 主入口：`https://qinghecircle.dpdns.org`
- 技术栈：Flask、Jinja2、PostgreSQL、SQLAlchemy、Vercel、Neon、Cloudflare
- 当前版本已部署；发布前必须完成自动化回归、公网 smoke、密钥检查和文档同步。

## 阅读顺序

1. `docs/0-pre-development/01-问题定义.md`
2. `docs/0-pre-development/02-可行性研究报告.md`
3. `docs/0-pre-development/03-项目开发计划.md`
4. `docs/0-pre-development/04-已确认范围与约束.md`
5. `docs/00-governance/engineering-standards.md`
6. `docs/00-governance/collaboration-and-quality-gates.md`
7. `docs/00-governance/glossary.md`

## 唯一标准

- 技术标准以 `docs/00-governance/engineering-standards.md` 为准。
- 业务术语以 `docs/00-governance/glossary.md` 为准。
- 阶段和质量门禁以 `docs/00-governance/collaboration-and-quality-gates.md` 为准。
- 范围、接口、数据库或业务规则变更必须记录在 `docs/00-governance/decision-log.md`。
- 开发文档只维护一套，不创建重复规范或平行实现。

## 开发原则

- 保持 `route -> service -> model/database` 的依赖方向。
- 业务规则、权限和事务放在 service 层；路由只负责协议转换。
- 新模块通过明确的 service 接口扩展，避免跨模块直接依赖内部实现。
- 一项变更应同时包含实现、测试、文档和必要的数据库迁移。
- 未经测试证据支持，不宣称功能完成或发布安全。

## 发布检查

1. 需求、设计和决策记录已同步。
2. 数据库迁移已在可回滚的演练环境执行。
3. 自动化测试和静态检查通过。
4. Preview 与 Production smoke 通过。
5. 未提交密码、验证码、连接串、Access Key、API Token 或真实个人信息。
6. 公开文档不包含凭据、内部工作记录和不应公开的运营信息。

## 安全底线

- 真实密钥只放在 `.env.local`、Vercel Secrets 或平台密钥管理中。
- 不提交密码、验证码、数据库连接串、R2 Access Key、R2 Secret、API Token。
- 不在日志或测试报告中输出学生手机号、密码和完整连接串。
- 真实支付、公开募捐和公益资金不进入当前版本；真实短信只用于学生注册验证。

