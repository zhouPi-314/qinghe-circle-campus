# 青禾流转 6.2 数据库设计说明书

| 项目 | 内容 |
|---|---|
| 文档编号 | DES-DB-001 |
| 版本 | 1.1 |
| 日期 | 2026-11-19 |
| 状态 | 已批准并冻结 |
| 数据库 | PostgreSQL 18 |
| 字符集 | UTF-8 |
| 时区 | 存储 UTC，界面显示 Asia/Shanghai |
| 建表脚本 | `sql/schema.sql` |
| 演示数据 | `sql/seed.sql` |

## 1. 设计原则

- 主键统一使用 `bigint generated always as identity`。
- 所有业务对象都直接保存 `university_id`，或能通过强制外键追溯到高校。
- 活动申请互斥在数据库和服务层同时防护：数据库阻止第二条第活动申请，服务层给出可理解错误。
- 金额以整数分保存，命名为 `_cents`；项目不保存真实支付账户和资金流水。
- 手机号不作为可回显明文保存。名单和账号使用规范化手机号的 HMAC-SHA-256 值进行匹配，另存后四位用于人工识别。
- 非学生管理员使用唯一 `login_name` 登录；学生使用学号或手机号登录，不创建管理员账号名。
- 文件只保存 R2 对象 key、类型、大小和校验信息，不保存本机临时路径。
- 业务状态使用短英文代码和数据库 `check` 约束，页面通过统一映射显示中文。
- 关键历史只追加。争议、状态、审核和导入不得通过覆盖记录抹去历史。

## 2. 表规模核算

概念模型最初得到 27 张表；G5 增加 4 张注册验证与运维安全表，当前共 31 张：

| 分组 | 表数 | 表 |
|---|---:|---|
| 组织与账号 | 9 | `universities`、`campuses`、`users`、`stations`、`station_manager_assignments`、`student_import_batches`、`student_registry_records`、`login_verification_codes`、`registration_verification_requests` |
| 物品与发布 | 3 | `item_categories`、`items`、`item_images` |
| 申请与履约 | 6 | `circulation_requests`、`borrow_details`、`sale_details`、`recycle_details`、`handover_records`、`status_history` |
| 治理与通知 | 7 | `notifications`、`disputes`、`dispute_messages`、`audit_logs`、`security_events`、`security_blocks`、`application_events` |
| 公益首版 | 6 | `charity_projects`、`charity_project_needs`、`charity_donations`、`charity_donation_items`、`charity_receipts`、`charity_receipt_items` |

数量是建模结果，不是设计目标。没有为达到某个数字而增设空表。

### 2.1 四川省高校种子数据

`universities` 和 `campuses` 首批导入教育部 2025 年全国普通高等学校名单中的四川省普通高校：

- 高校 141 所，包含学校全称、学校标识码、所在地、办学层次、办学性质和主管部门。
- 校区记录 161 条，每所高校至少一条主校区记录。
- 10 所多校区高校使用学校官网公开的校区名称，并将校区记录标记为 `official`。
- 其余高校暂以学校全称作为单校区名称，标记为 `temporary`，后续可根据学校官网继续核验。
- 数据源与生成结果保存在 `data/sichuan_universities_2025.csv` 和 `sql/seed.sql`。

## 3. 统一字段约定

| 字段 | 规则 |
|---|---|
| `id` | `bigint generated always as identity` 主键 |
| `university_id` | 业务隔离根；适用于高校范围的直接对象 |
| `campus_id` | 仅用于有明确校区归属的对象 |
| `status` | 由 `check` 约束限制在业务状态集合 |
| `created_at` | `timestamptz not null default now()` |
| `updated_at` | 由应用在事务中更新；不依赖前端时间 |
| `created_by_user_id` | 创建人；无人类创建者的系统记录可为空 |
| `object_key` | Cloudflare R2 对象 key，不保存 URL、临时路径或密钥 |
| `reason` / `note` | 拒绝、取消、争议和审核必须允许记录原因 |
| `login_name` | 公益管理员、平台管理员和校级管理员的唯一登录账号；学生为空 |

## 4. 关键完整性规则

### 4.1 高校隔离

- `items`、`users`、`stations`、`charity_projects`、`charity_receipts` 直接保存高校标识。
- 申请记录同时保存物品、申请人和所有者所属高校，并使用复合外键防止同一条记录混入两所学校。
- 服务层每次读取对象后再次校验 `actor.university_id`；数据库只作为第二道防线。
- 平台管理员可以跨高校维护基础数据，但所有写操作写入 `audit_logs`。

### 4.1.1 登录身份与注册

- 登录前先选择在校学生、公益管理员、平台管理员或校级管理员。
- 只有在校学生可以进入学校—校区选择并自主注册。
- 公益管理员和校级管理员账号由平台管理员导入，不显示注册入口。
- 平台管理员首版只预置 1 个账号，不设账号总数上限。
- 校级管理员按本校范围管理组织、账号名单、审核、争议和审计。

### 4.2 活动申请唯一

`circulation_requests` 中的以下状态视为活动：

```text
pending
accepted
payment_pending
handover_pending
in_progress
return_pending
inspection_pending
disputed
```

数据库使用部分唯一索引保证同一物品最多有一条活动申请。拒绝、取消或完成后解除占用。

### 4.3 模式一致性

- `circulation_requests.mode` 必须与对应 `items.mode` 一致。
- `borrow_details`、`sale_details`、`recycle_details` 与申请一对一。
- `recycle_details` 才能引用回收站点。
- `sale_details` 仅在出售模式存在；价格使用分保存。
- 赠送模式没有专属明细表，由统一申请、交接和完成状态覆盖。

### 4.4 交接码

- 只保存验证码哈希，不保存明文。
- 默认 6 位数字、10 分钟有效、一次使用。
- 重新生成时增加 `code_version` 并覆盖活动哈希；旧码立即不可验证。
- 生成人和使用人必须是该申请的权利双方，且同属一所高校。

### 4.5 公益数量

- 项目需求维护 `target_quantity` 与 `accepted_quantity`。
- 数据库约束 `accepted_quantity <= target_quantity`。
- 服务核验时锁定需求行，重新读取已接收数量后累加，避免并发超募。
- 回执数量不能大于对应已接收捐赠物资数量。
- 捐赠资料只保存数量、说明和物资图片，不保存受助儿童的姓名、电话、地址或清晰人脸。

## 5. 索引设计

| 索引 | 目的 |
|---|---|
| `users(university_id, role, status)` | 高校用户列表和角色筛选 |
| `student_registry_records(university_id, student_no)` 唯一 | 注册时快速匹配且阻止重复学号 |
| `student_registry_records(university_id, phone_hash)` 唯一 | 阻止重复手机号绑定 |
| `items(university_id, status, mode, category_id)` | 本校物品浏览和筛选 |
| `items(owner_user_id, created_at desc)` | 我的物品 |
| `circulation_requests(item_id) where status in active_statuses` 唯一 | 活动申请互斥 |
| `circulation_requests(requester_user_id, created_at desc)` | 我的申请 |
| `circulation_requests(owner_user_id, status, created_at desc)` | 待我处理 |
| `handover_records(code_hash)` 唯一 | 一次性交接码验证 |
| `notifications(recipient_user_id, read_at, created_at desc)` | 未读通知 |
| `charity_projects(university_id, status, deadline)` | 本校公益项目 |
| `charity_project_needs(project_id, status)` | 项目目标和进度 |
| `charity_donations(station_id, status, created_at)` | 站点待核验捐赠 |
| `audit_logs(university_id, created_at desc)` | 高校审计查询 |

## 6. 个人数据和隐私

| 数据 | 存储方式 | 使用方式 |
|---|---|---|
| 学生姓名 | 名单表保存，页面只在必要管理场景显示 | 不公开展示 |
| 学生手机号 | `phone_hash` + `phone_last4` | 注册、登录校验；管理员仅看到掩码 |
| 学号 | 普通文本 | 本校内部识别，不进入公开物品页面 |
| 密码 | 不可逆慢哈希 | 不记录明文、不写日志 |
| 验证码 | 带作用域的哈希 | 一次性校验 |
| 头像与物品图片 | R2 对象 key | 通过受控公开或签名访问 |
| 公益受助对象 | 仅保存非识别性的公开说明 | 不保存儿童姓名、地址、联系方式或清晰人脸 |

## 7. 删除与保留

- 用户、物品、申请、捐赠和回执默认不物理删除。
- 用户和物品使用 `status` 停用或下架；管理员操作写入审计。
- 申请完成后保留申请、明细、交接和状态历史。
- 站内通知可归档，不作为业务证据的唯一来源。
- 审计日志不得由普通管理员删除；应用也不提供页面删除入口。

## 8. 初始化与回放

`sql/schema.sql` 负责结构，`sql/seed.sql` 写入四川省高校目录和基础分类，不写入真实学生名单、公益对象资料或固定管理员密码。公开版首次部署使用 `tools/create_platform_admin.py` 交互创建管理员。

初始化顺序：

```text
createdb qinghe_circle
psql -d qinghe_circle -f sql/schema.sql
psql -d qinghe_circle -f sql/seed.sql
```

进入 6.3 后，种子账号密码和完整演示数据由实现阶段补齐；数据库结构已在本阶段冻结。

<!-- docx-page-break -->

## 9. 与需求的映射结果

| SRS 范围 | 对应表 |
|---|---|
| 多高校与校区 | `universities`、`campuses` |
| 学生名单核验 | `student_import_batches`、`student_registry_records` |
| 账号、角色、头像和验证码 | `users`、`login_verification_codes` |
| 回收/公益站点 | `stations`、`station_manager_assignments` |
| 物品、分类、图片 | `item_categories`、`items`、`item_images` |
| 四类流转和交接 | `circulation_requests`、`borrow_details`、`sale_details`、`recycle_details`、`handover_records` |
| 状态、通知、争议和审计 | `status_history`、`notifications`、`disputes`、`dispute_messages`、`audit_logs` |
| 公益项目、捐赠、进度和回执 | `charity_projects`、`charity_project_needs`、`charity_donations`、`charity_donation_items`、`charity_receipts`、`charity_receipt_items` |

## 10. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-11-19 | 建立数据库结构、约束、索引、隐私和初始化规则 |
| 1.1 | 2026-11-19 | 明确平台管理员只预置 1 个，不设账号总数上限 |
