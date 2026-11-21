# 青禾流转工程标准

本文档是项目唯一技术标准。Codex 和 WorkerBuddy 均按本文件执行。

## 1. 技术栈

- Python 3.13
- Flask 3.x
- Jinja2 服务端模板
- Flask-SQLAlchemy + SQLAlchemy 2.x
- PostgreSQL 18
- `psycopg` 3.x
- pytest
- Ruff
- boto3（R2 S3-compatible API）
- alibabacloud-dypnsapi20170525（阿里云短信认证）
- Pillow（图形验证码）

首版保持 Web-only、服务端渲染。不引入 React、Vue、SPA、REST API、微服务、消息队列或第二套 ORM。

## 2. 目录结构

```text
app/
├── __init__.py
├── core/
│   ├── auth.py
│   ├── errors.py
│   ├── permissions.py
│   └── storage.py
├── models/
│   ├── university.py
│   ├── user.py
│   ├── item.py
│   ├── circulation.py
│   └── charity.py
├── services/
│   ├── auth_service.py
│   ├── item_service.py
│   ├── circulation_service.py
│   └── charity_service.py
├── routes/
│   ├── auth.py
│   ├── items.py
│   ├── circulation.py
│   └── charity.py
├── templates/
└── static/
sql/
├── schema.sql
└── seed.sql
tests/
├── unit/
├── integration/
├── acceptance/
└── fixtures/
```

文件可以按实际业务拆分，但职责层级保持不变。

## 3. 模块职责

依赖方向：

```text
route/blueprint → service → model/database
```

- Route：解析请求、调用服务、返回模板或重定向。
- Service：业务规则、权限判断、事务和状态转换。
- Model：持久化结构、字段约束和关系。
- Template：展示数据，不执行数据库查询或核心业务判断。
- Core：跨模块的安全、错误、权限和存储适配器。

Service 的公开函数是模块接口。接口要隐藏复杂实现，调用方和测试通过同一接口验证行为。

不增加仅做透传的 Repository、Manager、Helper 或无第二个实现的 Adapter。

## 4. 数据与事务

- 所有业务表必须有 `university_id` 或可追溯到高校的强制外键。
- 同校跨校区允许；跨学校操作必须拒绝。
- 状态变更使用 service 内的单事务完成。
- 主键使用 PostgreSQL Identity。
- 时间统一存 UTC，页面按 Asia/Shanghai 展示。
- `sql/schema.sql` 是首版数据库结构唯一来源。
- 数据结构变更必须更新 `decision-log.md` 并提供迁移说明。
- 禁止在模板、路由或测试夹具中复制另一套表结构定义。

## 5. 权限与安全

- 四类业务角色：在校学生、公益管理员、平台管理员、校级管理员；校级管理员只操作本校。
- 关键权限在 service 层再次校验，不能只依赖路由或页面隐藏。
- 对象操作校验归属、角色和高校范围。
- 密码只存哈希。
- 使用 CSRF 防护。
- 登录后会话 Cookie 设置 `HttpOnly`、`SameSite`，生产环境启用 `Secure`。
- 图片允许 JPEG、PNG、WebP；单文件最大 3 MB。
- R2 key 使用随机 UUID；数据库保存对象 key，不保存临时本地路径。
- 日志和错误页隐藏密码、验证码、数据库连接串、学生手机号和密钥。
- 注册短信使用 PNVS/Mock Provider seam；自动化测试不得访问阿里云。
- 同一 IP 注册短信滥用由数据库锁和临时封禁控制；Cloudflare 只作为可选边缘层。
- 生产环境关闭 Flask debug 和自动重载。

## 6. 页面与交互

- 页面标签、导航、按钮和错误信息使用中文。
- 代码标识、表名、字段名和函数名使用英文 `snake_case`。
- 状态显示使用统一中文名称，不自行发明同义状态。
- 基础响应式；核心流程可在手机浏览器完成。
- 错误必须给出下一步操作，不能只显示异常文本。

## 7. 测试

- WorkerBuddy 编写并执行 service 单元测试和模块集成测试。
- Codex 独立编写 `tests/acceptance/`，按需求与设计验收。
- WorkerBuddy 不修改 `tests/acceptance/`，发现验收标准问题应提交变更申请。
- 集成测试使用 PostgreSQL，不用 SQLite 替代线上方言。
- 外部 R2 调用在单元测试中使用 fake；至少有一条真实 R2 集成 smoke test。
- 所有测试结果必须记录命令、commit、环境和结果路径。

最小测试覆盖范围：

- 注册、登录、退出和角色权限；
- 高校隔离和同校跨校区；
- 四类流转及异常状态；
- 公益募集、捐赠和回执；
- 图片上传失败和回滚；
- 空数据库初始化；
- Vercel/Neon/R2 公网 smoke test。

## 8. 文档规范

- 每个阶段使用独立目录，不把代码说明散落在聊天记录中。
- 阶段文档必须有版本、日期、状态和变更记录。
- 业务规则变更先更新文档，再改代码。
- 术语使用 `glossary.md` 中的定义。
- 代码变更与文档变更在同一次交付中同步提交。

## 9. Git 规范

分支：

- `main`：已批准版本
- `workerbuddy/6.3-implementation`
- `codex/6.3-acceptance`

提交前缀：

- `feat:`
- `fix:`
- `test:`
- `docs:`
- `refactor:`
- `chore:`

WorkerBuddy 与 Codex 的修改必须可区分。禁止在他人仍持有写入权时直接覆盖其工作。

## 10. 完成定义

一个增量只有同时满足以下条件才算完成：

- 对应业务规则已实现；
- 权限和高校隔离已校验；
- 单元或集成测试通过；
- 页面错误路径可操作；
- 阶段文档同步更新；
- 无新增明文密钥；
- 可重复启动；
- 没有未记录的跨模块接口变化。

