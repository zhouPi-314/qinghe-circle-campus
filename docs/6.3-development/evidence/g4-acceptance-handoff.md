# G4 验收交接材料（WorkerBuddy → Codex）

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 依据 | D-040：用户书面批准 G3 通过，进入 G4 发布候选阶段 |
| WorkerBuddy 状态 | 已停止新增功能与提交；本材料为验收输入，不包含业务代码变更 |

## 1. 验收基线

| 项 | 值 |
|---|---|
| 分支 | `workerbuddy/6.3-implementation` |
| 代码 commit | `[private-history]`（G4 前加固，183 项测试） |
| 文档/证据 commit | `[private-history]` |
| 前置门禁 | G0（D-031）、G1（D-035）、G2（D-037）、G3（D-038 修复重提交 + 复审通过，D-040 正式批准） |
| 加固决策 | D-039（行锁并发加固 + 公开文本 PII 规则检测） |

## 2. 复现命令

```bash
# 测试（本地 PostgreSQL 18，连接串在 .env.local，不入库）
.venv/Scripts/python.exe -m pytest          # 183 passed（含 2 项真实 R2 smoke）
.venv/Scripts/python.exe -m ruff check app tests

# 测试库按运行独立（qinghe_circle_test_<pid>，会话后自动删除）
# 数据库结构唯一来源 sql/schema.sql（27 表，未修改）；演示数据 sql/seed.sql
```

Python 3.13.14；依赖见 `docs/6.3-development/evidence/g3-dependencies.txt`（加固未新增依赖）。

## 3. 证据文件索引

| 文件 | 内容 |
|---|---|
| `docs/6.3-development/evidence/g3-gate-report.md` | G3 门禁报告 v2（12 项退回修复对照表） |
| `docs/6.3-development/evidence/g4-hardening-report.md` | G4 前加固说明（锁范围/PII 字段/非目标/已知限制） |
| `docs/6.3-development/evidence/g3-test-output.txt` 等 | G3 轮测试输出与依赖清单 |
| `docs/00-governance/decision-log.md` | D-031 ~ D-040 全部决策记录 |

## 4. 待 Codex 验收的重点（WorkerBuddy 自报关注项）

1. **并发锁实现**（D-039）：锁序声明（申请行→物品行、争议行→申请行→物品行、申请行→交接记录行、需求/明细行按 ID 升序）是否与实现一致；`populate_existing` 是否覆盖全部锁内重读；
2. **PII 检测边界**（D-039）：公开字段接入清单与 BR-039 的符合性；donor_note/request_note/争议/审计不过滤是否可接受；
3. **D-033 发布检查项**：轮换 SECRET_KEY 前必须执行手机号哈希迁移（平台管理员重导名单 → 按 registered_user_id 同步 registry→users）；未执行迁移前禁止轮换 SECRET_KEY——请纳入 G4 发布检查单；
4. **真实 R2 smoke**：凭据存在时 2 项实际执行（上传→读回→删除、唯一键 try/finally 清理）；
5. **公网部署 smoke test**：按门禁由 Codex 在 G4 执行公网验收覆盖（WorkerBuddy 未部署 Production，等待用户批准）。

## 5. 已知问题与偏差（沿 G3/G4 加固记录）

1. 公益捐赠 `dispatched_at`（回执发放时间）无表单入口；
2. 高校"编辑"通过下拉选择 + 表单提交实现，交互较简；
3. PII 规则检测覆盖手机号/身份证/邮箱三类，不覆盖地址、姓名等弱结构化信息；
4. 并发验证为线程级课堂演示，非生产级压测；
5. 交接码通知文案采用通用表述（低风险偏差）。

## 6. WorkerBuddy 在 G4 的承诺

- 不修改业务代码，等待缺陷清单；
- 收到退回缺陷后按清单修复并再次停止；
- 不执行 Production 部署，等待用户批准。
