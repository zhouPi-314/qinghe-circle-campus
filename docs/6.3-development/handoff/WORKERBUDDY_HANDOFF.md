# WorkerBuddy 6.3 开发交接书

| 项目 | 内容 |
|---|---|
| 项目 | 青禾流转（Qinghe Circle Campus） |
| 交接文档版本 | 1.9 |
| 生成日期 | 2026-11-20 |
| 状态 | G0～G4 已批准通过；用户于 2026-11-21 批准 G4 并授权发布（D-042）。项目进入 M6 发布与课程交付收尾，WorkerBuddy 保持停止 |
| AI 名称 | Codex |
| 需求版本 | SRS-001 1.1（已批准冻结） |
| 设计版本 | 6.2 设计集 1.9（其中 UI 1.7、设计审查 1.5） |
| 工程标准 | `docs/00-governance/engineering-standards.md` 现行基线 |
| 交接 commit | `1be11ed`（main 冻结基线）；实施分支 `workerbuddy/6.3-implementation` |
| 计划完成日期 | 2026-12-16 |

## 1. 交接结论

用户已于 2026-11-20 批准并冻结 6.1、6.2，本文件据此升级为正式 G0 交接。G0 已于 2026-11-20 完全通过（D-031）：Git 仓库与基线 commit 已建立，WorkerBuddy 实施确认已提交并获用户书面确认，G1 编码已获准进行。

6.2 已完成数据库、架构、权限、状态、页面和文件存储边界，内部审查无阻塞矛盾。实现阶段以 `sql/schema.sql`、service 接口和已批准设计为唯一依据，不以本交接书替代详细设计。

## 2. WorkerBuddy 开始前必须阅读

1. `AGENTS.md`
2. `docs/00-governance/engineering-standards.md`
3. `docs/00-governance/collaboration-and-quality-gates.md`
4. `docs/00-governance/glossary.md`
5. `docs/6.1-requirements/需求规格说明书.md`
6. `docs/6.1-requirements/业务流程图.md`
7. `docs/6.1-requirements/需求闭环检查.md`
8. `docs/6.2-design/01-data-model-and-er.md`
9. `docs/6.2-design/02-database-design.md`
10. `docs/6.2-design/03-architecture-design.md`
11. `docs/6.2-design/04-global-conventions.md`
12. `docs/6.2-design/05-ui-design-and-prototypes.md`
13. `docs/6.2-design/06-design-review.md`
14. 本交接书全部内容

以上路径现对应冻结基线。WorkerBuddy 不得修改 6.1、6.2、历史 AI 提示词或本文件中的 `Codex` 标识。

## 3. 当前基线

| 产物 | 当前状态 | 实现用途 |
|---|---|---|
| 6.1 需求规格 SRS-001 1.1 | 已批准冻结 | 业务范围和验收依据 |
| 6.2 数据模型 | 27 张有独立职责的表 | 实体、关系和约束依据 |
| `sql/schema.sql` | PostgreSQL 18 建表来源 | 首版唯一数据库结构 |
| `sql/seed.sql` | 基础演示数据 | 空库初始化后的课程演示 |
| `docs/6.2-design/prototype/index.html` | 设计评审原型 | 视觉和交互参考，不是产品代码 |
| 6.2 课程 Word | 当前 5 份已同步最新 UI | 课程交付与冻结设计参考 |
| 业务代码 | G1 基础骨架 + G2 共享借还闭环已实现（G2 代码 commit `bf3b36b`）；出售/赠送/回收与公益模块随后续增量 | G2 审核通过后按第 4 节顺序复制共享模式 |

已核验演示数据为 141 所四川省普通高校、161 条校区记录。公开版种子数据不再预置管理员账号，首次部署使用 `tools/create_platform_admin.py` 交互创建。多校区高校中以 `temporary` 标记的校区不得视为官网已核验数据。

## 4. 本轮必须实现

按以下顺序形成可运行增量，不按页面数量平均铺开：

1. Flask 应用骨架、配置、数据库连接、统一错误处理和应用工厂。
2. 高校、校区和站点作用域；所有业务对象必须可追溯到 `university_id`。
3. 身份选择、学生学校校区选择、名单核验注册、密码登录、模拟验证码和会话权限。
4. 物品发布、分类、浏览、筛选、图片和状态展示。
5. 共享借还完整闭环，作为第一条业务穿线。
6. 二手交易与模拟支付。
7. 免费赠送与绿色回收。
8. 一次性交接码、取消、逾期、归还、争议和状态历史。
9. 公益项目、实物捐赠、站点核验、募集进度和脱敏回执。
10. 管理端名单导入、账号、内容审核、争议、统计和审计。
11. 响应式页面、异常反馈、R2 fake、PostgreSQL 集成测试和部署 smoke test。

## 5. 明确不做

- 真实支付、退款、资金账户、资金流水或资金托管。
- 真实短信、真实邮件、实名认证或高校官方接口。
- 公益义卖、公益金、微心愿金额认领或真实公开募捐。
- 移动 App、微信小程序、React、Vue、SPA 或独立 REST API。
- 实时聊天、推荐算法、地图、骑手、物流和快递面单。
- 积分商城、优惠券及没有页面入口的占位模块。
- 6.2 未出现的新业务表、新角色或新核心依赖。

## 6. 允许依赖

首版技术栈限定为：

- Python 3.13
- Flask 3.x
- Jinja2
- Flask-SQLAlchemy + SQLAlchemy 2.x
- psycopg 3.x
- pytest
- Ruff
- boto3（Cloudflare R2 S3-compatible API）

WorkerBuddy 在 G1 必须提交 `requirements.txt` 或等价锁文件、Python 实际版本和完整依赖输出。新增核心依赖先停止并申请；不得引入第二套 ORM、任务队列、前端框架或微服务。

## 7. 模块与接口契约

依赖方向固定为：

```text
route/blueprint -> service -> model/database
```

Route 只解析请求和输出模板；Service 负责权限、状态、事务和业务规则；Model 只负责持久化结构与约束；Template 不查询数据库，也不自行判断业务状态。

| 模块 | Service 公开接口 | 主要职责 |
|---|---|---|
| 身份与准入 | `get_student_context()`、`register_student()`、`authenticate_password()`、`issue_login_code()`、`verify_login_code()`、`load_current_user()`、`update_profile()`、`import_students()`、`import_managed_accounts()` | 名单核验、两类登录、角色和资料 |
| 校园组织 | `list_universities()`、`create_university()`、`update_university()`、`list_campuses()`、`create_campus()`、`update_campus()`、`create_station()`、`assign_station_manager()`、`manager_scope()`、`get_organization_tree()` | 高校、校区、站点和授权 |
| 物品与媒体 | `create_item()`、`search_items()`、`get_visible_item()`、`update_item()`、`change_item_shelf_state()` | 物品、图片、可见范围和上下架 |
| 流转申请 | `request_borrow()`、`request_purchase()`、`request_giveaway()`、`request_recycle()`、`decide_request()`、`simulate_payment()`、`submit_return()`、`confirm_return()`、`inspect_recycle()` | 四类申请和模式状态 |
| 交接与异常 | `issue_handover_code()`、`confirm_handover()`、`cancel_request()`、`open_dispute()`、`add_dispute_message()`、`resolve_dispute()` | 交接码、取消、归还和争议 |
| 公益首版 | `create_project()`、`update_project_need()`、`submit_donation()`、`review_donation()`、`publish_receipt()` | 实物捐赠、核验、进度和回执 |
| 通知与审计 | `notify()`、`list_notifications()`、`mark_notification_read()`、`record_audit()` | 站内通知和关键操作记录 |

不得增加只做透传的 Repository、Manager、Helper 或单实现 Adapter。调用方通过 service 接口获得结果，不依赖内部表组合。

## 8. 数据库契约

`sql/schema.sql` 是首版唯一数据库结构来源；`sql/seed.sql` 是演示数据来源。WorkerBuddy 不得自行改字段、加表、删表或维护另一份模型定义。

27 张表按职责分组：

| 分组 | 表 |
|---|---|
| 高校与账号 | `universities`、`campuses`、`users`、`stations`、`station_manager_assignments`、`student_import_batches`、`student_registry_records`、`login_verification_codes` |
| 物品与流转 | `item_categories`、`items`、`item_images`、`circulation_requests`、`borrow_details`、`sale_details`、`recycle_details`、`handover_records` |
| 通知与治理 | `status_history`、`notifications`、`disputes`、`dispute_messages`、`audit_logs` |
| 公益首版 | `charity_projects`、`charity_project_needs`、`charity_donations`、`charity_donation_items`、`charity_receipts`、`charity_receipt_items` |

关键规则：

- 所有业务数据可追溯到高校；跨学校操作必须拒绝，同校跨校区允许。
- 同一物品同一时间最多一条活动申请；数据库部分唯一索引和服务层都要防护。
- 借用、出售、赠送、回收按各自主链推进，不允许跨模式跳转。
- 交接码为 6 位、10 分钟有效、一次性；重新生成后旧码失效。
- 公益数量必须使用 `accepted_quantity <= target_quantity` 并在服务层锁定需求行。
- 主键使用 PostgreSQL Identity；时间存 UTC，页面按 `Asia/Shanghai` 显示。
- 状态历史、争议说明和审计记录只追加，不覆盖历史。

## 9. 页面与权限契约

| 路由 | 角色 | 主要动作 |
|---|---|---|
| `/auth/identity` | 游客 | 选择四类登录身份 |
| `/auth/student-context` | 游客 | 学生选择学校与校区 |
| `/auth/login` | 游客 | 进入所选身份的登录界面 |
| `/auth/register` | 游客 | 仅在校学生名单核验注册 |
| `/items`、`/items/<id>` | 在校学生以上 | 浏览本校物品与详情 |
| `/items/new` | 在校学生 | 发布物品 |
| `/requests/<id>` | 约定双方或管理员 | 查看和推进流转 |
| `/charity`、`/charity/<id>` | 本校在校学生以上 | 查看项目与进度 |
| `/charity/<id>/donate` | 在校学生 | 提交本校实物捐赠 |
| `/charity/receipts/<id>` | 本校在校学生以上 | 查看已公示回执 |
| `/station`、`/station/recycling`、`/station/donations` | 公益管理员（回收） | 处理授权站点工作 |
| `/admin`、`/admin/organizations`、`/admin/student-imports`、`/admin/users` | 平台管理员 | 管理全局组织、账号和名单 |
| `/admin/moderation`、`/admin/disputes`、`/admin/audit` | 平台管理员 | 审核、争议和审计 |

所有写表单启用 CSRF；权限在 service 层再次校验。未登录跳转登录并保留目标页；角色越权返回 403；跨校对象返回 404 或无权限页，不泄露对象存在与否。错误页必须说明原因和下一步。

## 10. 文件与图片契约

- 首版由 Flask 服务端上传到 Cloudflare R2。
- 只允许 JPEG、PNG、WebP；单图最大 3 MB；单物品最多 5 张。
- 对象 key 使用随机 UUID；数据库只保存对象 key、类型、大小和必要元数据。
- 不保存浏览器直传配置、本地临时路径、永久公开签名或 R2 密钥。
- 单元测试使用 fake storage；至少一条真实 R2 集成 smoke test。
- 日志、错误页和测试报告不得输出手机号、密码、验证码、连接串或密钥。

环境变量只使用以下名称，值只放在 `.env.local` 或平台 Secret：

```text
SECRET_KEY
DATABASE_URL
CLOUDFLARE_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_ENDPOINT
R2_PUBLIC_BASE_URL
```

## 11. 实现与文档责任

WorkerBuddy 负责：

- `app/` 业务代码和 Jinja2 页面；
- `tests/unit/` 与 `tests/integration/`；
- 数据库和 R2 fake、R2 smoke test；
- 每个增量的启动说明、测试命令、结果和偏差记录；
- 在 G1、G2、G3 停止并提交可复现证据。

Codex 负责：

- 独立维护 `tests/acceptance/`；
- 设计符合性、安全、测试证据和部署验收；
- 受控修复与 G4 发布候选审查；
- 冻结点和阶段文档的一致性。

WorkerBuddy 不修改 `tests/acceptance/`。发现设计矛盾先停止，记录到 `docs/00-governance/decision-log.md` 并等待决定。

## 12. 强制暂停点

### G0：编码前

已于 2026-11-20 通过。补齐记录：

- 用户批准 6.1、6.2，冻结文档版本（已完成）；
- 建立 Git 仓库并生成交接 commit（已完成：`1be11ed`）；
- WorkerBuddy 提交实施确认且无阻塞问题（已完成；用户书面确认见 D-031）。

### G1：基础骨架

必须停止并提交：Flask 可启动、PostgreSQL schema 可初始化、基础鉴权和角色可用、健康页和错误页可用、基础测试通过、固定 commit。

### G2：第一条业务闭环

必须停止并提交：一条共享借还从创建到完成、正常与异常分支、权限与高校隔离、service/route/model/template/tests 和固定 commit。

### G3：全功能完成

必须停止并提交：四类流转、公益首版、完整测试、数据库和种子数据、已知问题、设计偏差和固定 commit。

### G4：发布候选

Codex 完成独立验收、安全审查、受控修复和最终回归；WorkerBuddy 按缺陷清单修复后再次停止。用户批准前不得部署 Production。

## 13. G0 当前阻塞

已于 2026-11-20 全部解除（见 D-030、D-031）：

| 阻塞项 | 影响 | 解除记录 |
|---|---|---|
| 当前目录没有 Git 仓库 | 无法提供可追踪交接 commit | 已初始化，基线 commit `1be11ed` |
| WorkerBuddy 尚未提交实施确认 | 无法证明已完成必读和接口理解 | 已按第 14 节模板提交，用户书面确认（D-031） |

## 14. WorkerBuddy 实施确认

WorkerBuddy 在 G0 只能提交以下确认，不得同时写业务代码：

```text
项目：青禾流转
需求版本：SRS-001 1.1（已批准冻结）
设计版本：6.2 设计集 1.9（已批准冻结）
工程标准版本：docs/00-governance/engineering-standards.md 现行基线
已阅读全部必读文档：是
本轮范围：G0 实施确认
明确不做：真实支付、短信、公开募捐、App、小程序、推荐、地图和物流
计划模块：身份准入、校园组织、物品媒体、流转申请、交接异常、公益首版、通知审计
计划数据库改动：无；仅使用 sql/schema.sql
计划新增依赖：无；精确版本在 G1 锁定
发现的问题：无/列表
我理解 G0、G1、G2、G3、G4 必须停下等待审阅：是
等待：Codex/用户确认
```

## 15. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 0.1 | 2026-11-20 | 根据 6.1、6.2 当前基线生成 G0 预交接，列明范围、接口、数据库、测试和阻塞项 |
| 1.0 | 2026-11-20 | 用户批准并冻结 6.1、6.2；升级为正式 G0 交接，保留 Git commit 与 WorkerBuddy 确认门禁 |
| 1.1 | 2026-11-20 | WorkerBuddy 按审核要求同步状态字段：G0 书面确认补录（D-031）、G0 阻塞解除；G1 首次提交退回修复中（D-032）。业务范围、接口与数据库契约未改动 |
| 1.2 | 2026-11-20 | WorkerBuddy 按第二次审核修正遗留矛盾：文档版本号、交接 commit、第 1 节交接结论与第 3 节业务代码状态与实际仓库对齐；G1 第二次提交修复中（D-034） |
| 1.3 | 2026-11-20 | G1 通过审核（D-035）；G2 共享借还闭环提交，状态字段同步 |
| 1.4 | 2026-11-20 | 用户批准 G2（D-037）；G3 四类流转（出售/赠送/回收）与公益首版、管理端、图片上传提交审核；修复 sale 接受后进入 payment_pending 的状态机路由、物品详情页图片上传块错位、站点工作台端点引用等缺陷 |
| 1.5 | 2026-11-20 | Codex 退回 G3（D-038）；WorkerBuddy 修复全部 12 项（分层下沉、文件签名校验+真实 R2 smoke、管理端审计、所有权转移、中文表头、公益项目页面、回执站点范围与累计防虚报、核验并发锁序、捐赠图片、站点类型、BR-043 异常冻结）；156 项测试全过，重提交等待复审 |
| 1.6 | 2026-11-20 | G3 复审通过；G4 前加固完成（D-039）：PostgreSQL 行锁并发加固（申请/状态操作/交接码/公益核验与回执/图片计数，锁序统一）、公开文本 PII 规则检测（手机号/身份证/邮箱，图片人工核验）、高校枚举对齐 schema、恶意数值 4xx；183 项测试全过；详见 docs/6.3-development/evidence/g4-hardening-report.md |
| 1.7 | 2026-11-21 | 用户书面批准 G3 通过、授权进入 G4（D-040）；WorkerBuddy 停止新增功能，提交 G4 验收交接材料（evidence/g4-acceptance-handoff.md），等待 Codex 独立验收、安全审查、受控修复与最终回归 |
| 1.8 | 2026-11-21 | Codex 完成 G4 验收并记录 D-041：修复公网物品页 500 和平台概览统计显示，最终 189 项测试全过；公网页面、权限、数据库写与审计、R2、安全 Cookie、桌面/移动视口通过；生产管理员密码已轮换；等待用户最终批准发布 |
| 1.9 | 2026-11-21 | 用户书面批准 G4 并授权发布（D-042）；G4 门禁关闭，项目进入 M6 发布与课程交付收尾；WorkerBuddy 保持停止 |
