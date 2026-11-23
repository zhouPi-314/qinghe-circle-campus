# G4 前加固报告（G4 HARDENING，D-039）

| 项目 | 内容 |
|---|---|
| 阶段 | G3 复审通过后、G4 发布候选前的可用性加固 |
| 决策记录 | `docs/00-governance/decision-log.md` D-039 |
| 前置门禁 | G0（D-031）、G1（D-035）、G2（D-037）、G3（复审通过） |
| 报告日期 | 2026-11-20 |
| 范围约束 | 不重构项目、不修改 `sql/schema.sql`、不新增表/角色/核心依赖；禁用 Redis、Celery、分布式锁、消息队列、机器学习模型 |

## 1. 并发锁范围（全部为 PostgreSQL 行锁 SELECT ... FOR UPDATE）

| 场景 | 锁方案 | 锁序 |
|---|---|---|
| 四类申请创建（借用/购买/赠送/回收） | `_lock_item`：锁物品行并重检 university_id/mode/status；冲突返回 `ConflictError("该物品已被其他人申请…")`，不依赖 IntegrityError | 物品行 → 申请行（申请行尚不存在） |
| decide_request / submit_return / confirm_return / simulate_payment / inspect_recycle | `_get_request(for_update=True)` 申请行锁，锁内重检状态；触达物品时 `_lock_item_row` | 申请行 → 物品行 |
| issue_handover_code / confirm_handover | 先锁申请行，再锁 handover_records 行；并发确认只有一个成功，另一个得到 ConflictError；重生成与确认互斥，旧码不得在新码生成后消费 | 申请行 → 交接记录行 → 物品行 |
| cancel_request / open_dispute / resolve_dispute | 申请行锁 / 争议行锁；resolve_dispute 锁序 争议行 → 申请行 → 物品行 | 同上 |
| review_donation | 锁捐赠行重读状态；按 **project_need_id 升序**一次性锁定本次涉及的需求行后判断超募（BR-036） | 捐赠行 → 需求行（升序） |
| publish_receipt | 按 **donation_item_id 升序**一次性锁定相关 charity_donation_items 行，再执行历史合计 + 本次校验（BR-038） | 明细行（升序） |
| add_item_image | 先锁物品行再统计图片数量（并发不突破 5 张）；数据库提交失败尽力删除刚上传的 R2 对象，失败只记录不含密钥的警告，不覆盖原异常 | 物品行 |

锁内重读全部使用 `execution_options(populate_existing=True)` 强制刷新已缓存实体，避免读旧状态。

## 2. PII 检测范围（app/core/privacy.py，D-039）

- 识别类型：中国大陆手机号（连续 11 位及 138-8000-1234 / 138 8000 1234 分隔形式）、18 位身份证号（含末位 X）、电子邮箱；
- 接口：`detect_pii(text)` 返回类型列表；`ensure_public_text_safe(text, field_name)` 命中即抛 `InputError`（默认拒绝提交，不静默改写原文）；
- 已接入的公开字段：
  - `item_service.create_item / update_item`：title、description；
  - `charity_service.create_project`：title、description、recipient_org、public_summary；
  - `charity_service._add_need`：item_name；
  - `charity_service.publish_receipt`：title、recipient_org、public_note、回执明细 item_name 与 note；
- 不做强制过滤（仅参与方或管理员可见）：donor_note、request_note、争议 reason/message、内部审计说明；
- 图片 PII：不做 OCR 或人脸识别，保留管理员人工核验；物品图片与捐赠图片页面已加提示"图片不得包含身份证、联系方式或清晰的个人人脸。"；
- 表单错误页统一返回 400（原位提示保持可读），恶意数值参数（负数确认数量、非法 decision/outcome、非整数解析）得到 4xx 中文错误而非 500。

## 3. 非目标

- 不做真实支付/短信/公开募捐；不引入分布式锁、消息队列、版本列或锁表；
- 不做图片 OCR/人脸识别与自动脱敏改写；
- 不修改 `sql/schema.sql`（高校枚举以现有 CHECK 约束为准，页面删除"中外合作办学"选项）；
- 不扩展图片删除功能；不新增表、角色或核心依赖。

## 4. 测试证据

- 命令：`.venv/Scripts/python.exe -m pytest`；**183 项全部通过**（原 156 + 新增 27）；
- 新增 `tests/unit/test_privacy.py`（9 项）：识别、不误报（"2024级软件工程，目标100件，金额88.00元"）、拒绝不改写；
- 新增 `tests/integration/test_g4_hardening.py`（18 项）：专科创建/非法枚举拒绝、恶意值 InputError 与 HTTP 400、并发申请互斥（含跨模式）、并发确认交接码（历史与通知只一次）、并发回执累计不超 accepted_quantity、HTTP 公开文本 PII 三入口；
- Ruff：`ruff check app tests` 全过；
- 真实 R2 smoke：凭据存在时运行（本轮 2 项实际执行），唯一键测试改为 try/finally 清理上传对象。

## 5. 已知限制

1. PII 规则检测覆盖手机号/身份证/邮箱三类，不能覆盖地址、姓名等弱结构化信息；开发验证足够；
2. 并发测试通过线程 + 独立数据库连接验证行锁互斥，不代表生产级压测；
3. 公益捐赠 `dispatched_at` 仍无表单入口（沿 G3 已知问题）；
4. 公网部署 smoke test 仍留待 G4 由 项目维护者 公网验收覆盖。
