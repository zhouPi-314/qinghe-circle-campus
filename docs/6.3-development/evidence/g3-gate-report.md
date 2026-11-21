# G3 门禁报告：四类流转与公益首版（v2，退回修复后重提交）

| 项目 | 内容 |
|---|---|
| 阶段 | G3 全功能完成（第二次提交，首轮审核退回项已全部修复） |
| 代码 commit | **`f0b4811`**（分支 `workerbuddy/6.3-implementation`）；首轮 G3 代码 commit `3fc7f7c` |
| 前置门禁 | G0（D-031）、G1（D-035）、G2（D-037，用户批准） |
| 报告日期 | 2026-11-20 |
| Python 版本 | **3.13.14**（见 `g3-python-version.txt`，v1 报告误写 3.13.12，已更正） |
| 测试命令 | `.venv/Scripts/python.exe -m pytest` |
| 测试结果 | **156 项全部通过**（本地 PostgreSQL 18 测试库，见 `g3-test-output.txt`） |
| Ruff | `ruff check app tests` 全过（见 `g3-ruff.txt`） |
| 依赖 | 见 `g3-dependencies.txt`；未新增 6.2 之外的依赖 |

## 0. 首轮审核退回项修复对照表

### Standards（4 项）

| # | 审核意见 | 修复 |
|---|---|---|
| S1 | 阻断：Route 直接执行数据库查询，破坏 route→service→database 分层 | admin.py、charity.py、items.py 路由中的 `db.session`/`select` 全部下沉：admin.py 改调 `org_service`（概览计数/校区/站点/管理员/高校维护）、`auth_service`（批次/账号/高校）、`item_service.list_recent_items`、`handover_service.list_open_disputes`；charity.py 改调 `charity_service.list_university_charity_stations/receipt_form_data`、`org_service.list_stations_for`；items.py 站点查询改调 `org_service.list_stations_for`。未新增透传 Repository |
| S2 | 阻断：R2 验收不完整；"图片类型"只信任浏览器 MIME | `storage.validate_image` 增加**文件签名（magic bytes）校验**（JPEG/PNG/WebP），任意内容伪装 image/jpeg 被拒；新增 `tests/unit/test_storage.py` 12 项（签名/伪造内容/FakeStorage/R2Storage mock boto3）；新增 `tests/integration/test_r2_smoke.py` 2 项**真实 R2 写入**（上传→读回→删除清理；凭据未配置时 skip 不伪造结论）。本轮凭据齐全，2 项真实 R2 测试实际执行通过 |
| S3 | 应修：管理端关键写操作未统一审计 | `org_service.create_campus/create_station/assign_station_manager/create_university`、`auth_service.import_students/import_managed_accounts` 均调用 `record_audit`（先 flush 取 Identity 主键再写审计）；`publish_receipt` 也补审计 |
| S4 | 阻断：门禁报告测试数量不准确（11/9/12 vs 实际 8/8/14）；Python 版本 3.13.12 vs 证据 3.13.14；交接书标题版本 1.3 vs 变更记录 1.4 | 本版报告按 `pytest --collect-only` 精确计数（见第 2 节）；Python 版本以证据文件为准（3.13.14）；交接书标题版本已同步（1.5） |

### Spec（8 项）

| # | 审核意见 | 修复 |
|---|---|---|
| P1 | 阻断：出售/赠送完成后未转移物品所有权，买家/领取人无法重新上架 | `handover_service.confirm_handover` 在 sale/give 交接成功时 `item.owner_user_id = request.requester_user_id`；测试断言新所有者可 relist（test_sale_loop、test_give_recycle_loop） |
| P2 | 阻断：名单导入页面要求中文表头，服务端只认英文 | `auth_service._normalize_csv_headers` 把 `学号,姓名,手机号,校区代码,年级,班级,专业,学院` 归一化为内部字段名；中文与英文表头均可导入（测试两种表头） |
| P3 | 阻断：公益项目创建/需求维护无页面路由；平台管理员不能维护高校 | 新增 `GET/POST /charity/projects/new`（公益管理员，含需求项表单）与 `POST /charity/<id>/needs`；新增 `org_service.create_university/update_university` + `/admin/organizations/universities` 路由与表单；模板 `charity/new_project.html`；base.html 增加入口 |
| P4 | 阻断：回执违反站点范围（可见其他站点数据、任意选 station_ids[0]）并可累计虚报 | `charity_service.receipt_form_data` 只返回**授权站点**已接收明细；`publish_receipt` 增加 `station_id` 参数且必须在授权范围内（FR-M03）；累计校验改为**历史回执合计 + 本次**（`func.sum` 聚合 `charity_receipt_items`）不得超过已接收数量；同一明细同回执重复登记同受约束；未核验明细不可登记回执 |
| P5 | 阻断：并发防超募不可靠（加锁前读状态、锁前 ORM 对象陈旧） | `review_donation` 改为：授权校验（不读行状态）→ `select(CharityDonation).with_for_update()` **锁捐赠行并重读状态** → 锁定需求行并以锁内最新值判断超募 |
| P6 | 应修：公益捐赠图片未实现；校验失败渲染不存在的 charity/donate.html → 500 | 新建 `charity/donate.html`（此前缺失）；捐赠表单按需求项支持可选图片上传（R2，`image_object_key` 入库），上传失败不阻断捐赠本体（flash 提示） |
| P7 | 应修：站点类型校验缺失（回收/捐赠可进不相容站点） | `request_recycle` 限 `recycle/mixed`（BR-029）；`submit_donation` 限 `charity/mixed`（FR-C02）；测试覆盖两类错配拒绝 |
| P8 | 应修：强制下架未真正下架/冻结，历史伪造 off_shelf | 按 BR-043 实现：有进行中业务 → **on_hold 异常冻结**；无业务 → 真正 off_shelf；已下架仅标 hidden；历史如实记录 from→to；另修复管理员 `university_id=None` 导致的误判跨校 NotFound |

### 附带修复（本轮发现）

- `auth_service.import_students` 的 `total_rows` 语义修正为数据行数（原记录最后一行行号，含表头）；
- admin 路由表单错误统一经 `_flash_input_error` 提示，不再吞掉非字段错误。

## 1. 功能清单（v1 报告内容仍然成立）

出售+模拟支付链、赠送链、回收链（站点授权/送达交接/验收/D-036）、公益首版（项目/需求/捐赠/行锁防超募核验/脱敏回执）、管理端（高校/校区/站点/授权、账号导入、名单导入、审核、争议、审计）、物品图片上传 R2 接线、捐赠图片（本轮补齐）。

## 2. 测试报告（精确计数，pytest --collect-only）

| 文件 | 数量 |
|---|---|
| tests/unit/test_states.py | 39 |
| tests/unit/test_storage.py | 12 |
| tests/unit/test_auth_validation.py | 9 |
| tests/integration/test_borrow_loop.py | 13 |
| tests/integration/test_sale_loop.py | **8** |
| tests/integration/test_give_recycle_loop.py | **8** |
| tests/integration/test_charity_loop.py | **16** |
| tests/integration/test_admin_g3.py | 14 |
| tests/integration/test_r2_smoke.py | 2（真实 R2） |
| tests/integration/test_permissions.py | 15 |
| tests/integration/test_register_and_login.py | 15 |
| tests/integration/test_health_and_errors.py | 5 |
| **合计** | **156** |

- v1 报告中"出售 11 / 赠送回收 9 / 公益 12"为编写时未按收集结果核对，实际为 8 / 8 / 16（公益 v2 又新增 4 项回执修复测试）；本版全部以收集输出为准。

## 3. 数据库脚本

无结构变更：继续使用冻结的 `sql/schema.sql`（27 表）与 `sql/seed.sql`。防超募、互斥、防虚报均由 schema 约束 + service 层防护实现。

## 4. 已知问题

1. 公益捐赠图片上传依赖对象存储配置；未配置 R2 时图片跳过（捐赠本体不受影响），表单有明确提示；
2. `dispatched_at`（回执发放时间）为可选字段，表单暂未提供输入入口；
3. 高校维护的"编辑"通过下拉选择 + 表单提交实现，交互较简。

## 5. 设计偏差清单

1. **D-036 已由 Codex 确认**（业务方向成立）：回收拒绝/验收不符合 → off_shelf，状态机转换 reserved→off_shelf、in_progress→off_shelf 维持实现；
2. 交接码通知文案采用通用表述（"与对方完成取件交接"），未按模式区分措辞；
3. 其余无偏差。

## 6. 证据文件

- `g3-test-output.txt`：pytest 完整输出（156 passed）；
- `g3-python-version.txt`：Python 3.13.14；
- `g3-dependencies.txt`：完整依赖清单；
- `g3-ruff.txt`：Ruff 全过输出。

## 7. 未执行项说明（沿首轮审核备注）

公网部署 smoke test 未执行：当前无生产地址，部署门禁在 G4 由 Codex 执行公网验收时覆盖。

## 8. 停止声明

按 `collaboration-and-quality-gates.md` 第 4 节，WorkerBuddy 修复完毕后停止，等待 Codex 重新审核。

```text
GATE READY: G3（重提交）
Commit: f0b4811（修复代码）；证据 commit 见 git log
Scope completed: 首轮 12 项退回项（4 Standards + 8 Spec）全部修复；156 项测试全过；真实 R2 smoke test 通过
Evidence: docs/6.3-development/evidence/g3-gate-report.md（v2）、g3-test-output.txt、g3-python-version.txt、g3-dependencies.txt、g3-ruff.txt
Deviations: 交接码通知文案通用化（低风险）；无其他
Blocking questions: 无
Waiting for: Codex review / user decision
```
