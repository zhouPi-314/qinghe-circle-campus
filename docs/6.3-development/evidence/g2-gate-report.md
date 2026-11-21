# G2 第一条业务闭环门禁报告（WorkerBuddy）

| 项目 | 内容 |
|---|---|
| 项目 | 青禾流转（Qinghe Circle Campus） |
| 门禁 | G2：第一条业务闭环（共享借还） |
| 提交者 | WorkerBuddy |
| 提交日期 | 2026-11-20 |
| **代码 commit** | **`[private-history]`**（分支 `workerbuddy/6.3-implementation`） |
| **证据 commit** | 本文件与测试证据所在 commit |
| 上一门禁 | G1 第三次提交通过（D-035） |
| 需求版本 | SRS-001 1.1（已批准冻结） |
| 设计版本 | 6.2 设计集 1.9（已批准冻结） |
| 等待 | Codex review / 用户确认 |

## 1. G2 完成标准核对

| 标准 | 结果 | 证据 |
|---|---|---|
| 共享借还从创建到完成的完整流程 | 通过 | 发布→申请→接受→交接码→取件→归还→确认完成（service + HTTP 双层测试） |
| 正常与异常分支 | 通过 | 拒绝、取消、错误码、过期码、旧版码失效、二次申请阻断、借期重叠、逾期显示、损坏转争议 |
| 权限与高校隔离 | 通过 | 路由守卫 + service 层 actor 校验；跨校对象 404 不泄露存在性 |
| service/route/model/template/tests 齐全 | 通过 | 见第 3 节结构 |
| commit 和测试日志 | `[private-history]` | evidence/g2-test-output.txt（文件头含 commit/分支/环境） |

## 2. 测试命令与结果

```text
命令：.venv/Scripts/python -m pytest tests（单进程串行）
结果：90 passed（单元 15：test_auth_validation 9 + test_states 6（新增）；
      集成 75：test_borrow_loop 13（新增）+ 既有 62）
Ruff：All checks passed!
耗时：42.43s（本地 PostgreSQL 18.6）
```

本轮新增测试（19 项）：
- 状态机单元测试 12 项：物品与申请的允许/禁止转换（含"交接后不可取消（BR-028）"、"冻结中不可恢复"等禁止跳跃）；
- 借还集成 7 项场景 + 1 条 HTTP 全链路：
  - 完整正常链（状态历史 5 步迁移断言 + 双方通知断言）；
  - 拒绝恢复可申请、申请人取消恢复可申请、交接后取消禁止；
  - 错误码不推进状态、过期码拒绝、重新生成旧码失效且新码可用；
  - 二次申请阻断（BR-012）、借期重叠守卫（BR-022，含不重叠通过的正例）；
  - 自我申请拒绝、跨校物品与申请 404（BR-002）；
  - 逾期动态计算 + 逾期仍可归还（BR-024）；
  - 归还损坏转争议 → 物品异常冻结 → 管理员处理关闭 + 审计记录（BR-023/041/042）；
  - HTTP 全链路：登录→发布→发现→申请→接受→生成交接码（明文一次性展示）→取件→归还→确认完成。

## 3. 共享模式与状态机实现说明（供 Codex 审查）

### 3.1 分层与模块

```text
app/core/states.py            状态集合、中文名、允许转换表、validate_*_transition
app/models/item.py            items / item_categories / item_images（映射 schema.sql）
app/models/circulation.py     circulation_requests / borrow_details / sale_details /
                              recycle_details / handover_records
app/models/governance.py      status_history / notifications / disputes /
                              dispute_messages / audit_logs
app/services/item_service.py  create_item / search_items / get_visible_item /
                              update_item / change_item_shelf_state
app/services/circulation_service.py  request_borrow / decide_request / submit_return /
                              confirm_return / get_request_detail / list_requests_for /
                              borrow_details_of / is_overdue / request_history
app/services/handover_service.py     issue_handover_code / confirm_handover /
                              cancel_request / open_dispute / open_dispute_for_request /
                              resolve_dispute / dispute_messages_for
app/services/notification_service.py notify / notify_users / list_notifications /
                              mark_notification_read / record_audit
app/routes/items.py           /items /items/new /items/<id>
app/routes/circulation.py     /items/<id>/borrow /requests/<id> 及 6 个状态操作 POST
app/templates/                items/discover / items/new / items/detail /
                              requests/detail / me/requests / me/notifications
```

依赖方向保持 route → service → model；service 以 `actor`（CurrentUser）为参并在内部复验角色与高校；模板不查询数据库（数据全部由路由经 service 组装）。

### 3.2 状态机

- 物品：active → reserved → in_progress → completed（借用主链）+ off_shelf/on_hold 分支；所有转换经 `validate_item_transition`（core/states.py 转换表来自 6.2 全局约定第 4 节）。
- 申请：pending → handover_pending → in_progress → return_pending → completed；disputed 从 return_pending/completed 进入、由管理员关闭；跨模式跳跃被禁止。
- 每次物品与申请状态变更写 `status_history`（同一事务），页面时间线读取同一数据。

### 3.3 事务边界

- 接受申请：借期冲突校验 → 申请状态迁移 → 物品状态迁移 → 状态历史 → 通知，单事务提交；
- 确认交接：交接记录一次性消费（status=used + consumed_*）与申请/物品状态迁移同事务；
- 争议开启：申请 disputed + 物品 on_hold + disputes/dispute_messages 写入 + 通知同事务；
- 活动申请互斥由数据库部分唯一索引兜底，服务层给出可理解错误（BR-012）。

### 3.4 交接码

- 6 位数字、10 分钟有效；哈希 = SHA256(SHA256(请求级盐+版本+码) + SECRET_KEY pepper)，只存哈希；
- 重新生成在原记录上 `code_version + 1` 并覆盖哈希，旧码立即失效（有测试断言）；
- 明文仅在生成交接码的当次响应 flash 中展示一次。

### 3.5 权限矩阵落实

| 操作 | 校验位置 |
|---|---|
| 发布物品 | 路由 `@roles_required("student")` + service `_require_student` + 校区归属 |
| 借用申请 | service：学生角色、非本人物品、模式一致、物品可申请、高校可见性 |
| 接受/拒绝/确认归还 | service `_get_request`：owner 校验 + 高校一致 |
| 提交归还/输入交接码/取消 | service：requester/双方校验 + 高校一致 |
| 生成交接码 | service：owner + 待交接状态 |
| 争议处理 | service：`actor.is_platform_admin` |
| 详情可见性 | 参与双方或管理员；其余一律 404 |

## 4. 数据库状态

- 未改 `sql/schema.sql`；未新增表/字段/索引；
- 开发库保持 141 高校 / 161 校区 / 1 平台管理员 / 0 学生（G1 证据后未污染）；
- 测试库按运行独立（`qinghe_circle_test_<pid>`，会话后删除）。

## 5. 偏差与后续增量说明

1. **物品图片上传（R2）延后**：`item_images` 模型已映射；上传/存储适配器随 G3 增量实现（交接书第 4 节第 4 条"图片"部分），G2 借还闭环不依赖图片。
2. **管理员争议处理页面**：`resolve_dispute` service 与审计已实现并有测试；`/admin/disputes` 页面随管理端增量（交接书第 4 节第 10 条）实现，G2 通过 service 层验证行为。
3. **编辑物品页**：`update_item` service 已实现并有字段校验；编辑表单页面随 G3 UI 增量接入（当前详情页提供下架/重新上架入口）。
4. **出售/赠送/回收**：按同一共享模式复制实现（交接书 G2 审查通过后执行），`sale_details`/`recycle_details` 模型已映射。

## 6. 已知问题

- 无已知功能问题。

## 7. 下一步

等待 Codex/用户对 G2 的审阅结论。通过后按同一共享模式复制实现出售、赠送、回收，随后是公益首版（G3 范围），在 G3 再次停止提交证据。
