# G1 基础骨架门禁报告 v3（第二次退回修复后重新提交）

| 项目 | 内容 |
|---|---|
| 项目 | 青禾流转（Qinghe Circle Campus） |
| 门禁 | G1：基础骨架（第三次提交） |
| 提交者 | WorkerBuddy |
| 提交日期 | 2026-11-20 |
| **代码 commit** | **`363b901eca58c70da3ec809bc8e8f8971cace751`**（分支 `workerbuddy/6.3-implementation`） |
| **证据 commit** | 本文件与测试证据所在 commit（见 `git log -- docs/6.3-development/evidence/`） |
| 上一版报告 | v2（代码 commit `9cfd12b`），第二次审核退回，结论记录于 D-034 |
| 需求版本 | SRS-001 1.1（已批准冻结） |
| 设计版本 | 6.2 设计集 1.9（已批准冻结） |
| 等待 | Codex review / 用户确认 |

## 0. 第二次退回项修复对照表

| # | Codex 退回项 | 修复方式 | 验证 |
|---|---|---|---|
| 阻断 | 管理员权限未在 service 层复验：`get_organization_tree()` 不接收操作者、无角色检查 | `org_service.get_organization_tree(actor)`：actor 为空或非 `platform_admin` 一律抛 `PermissionDeniedError`；路由传入 `g.current_user` | 新增 3 项 service 测试：匿名 actor 拒绝、学生 actor 拒绝、平台管理员通过（绕过路由直接调用） |
| 高 | 测试库不可并发（固定 `qinghe_circle_test`，重建 schema 引发锁冲突） | 每次运行使用独立测试库 `qinghe_circle_test_<pid>`，会话结束自动断开连接并 `DROP DATABASE` | conftest 重写；运行后复核 `leftover_test_dbs=0` |
| 中 | 手机号哈希与 SECRET_KEY 绑定，缺轮换迁移方案 | 密钥版本化派生（`PHONE_HASH_KEY_VERSION=1`）并在代码注释、D-033、本报告明确迁移路径：重导名单 CSV 重建 registry 哈希 → 按 `registered_user_id` 同步回 users → 学号登录恢复；纳入 G4 发布检查单，未迁移前禁止轮换 SECRET_KEY | D-033、app/core/auth.py `phone_hmac_key()` |
| 阻断 | 登录后无法返回原目标页（identity/student-context 丢 next） | `next` 贯穿整链：login→identity→student-context→login→落点；仅允许站内相对路径（拒绝 `//`、反斜杠、外链） | 新增端到端测试 `test_full_chain_returns_to_original_target`：6 步链路最终落点 `/me/profile` 200；另测 `//evil.com` 被丢弃 |
| 高 | 开发库被污染（142/162/2/1） | `tools/init_database.py --reset` 重建开发库；实测 `universities=141 campuses=161 platform_admins=1 students=0`；固定旧测试库 `qinghe_circle_test` 已删除 | psql 实测输出见第 3 节 |
| 高 | 交接书自相矛盾（版本 1.0、交接 commit 未生成、G0 未通过、业务代码未开始） | 交接书升版 1.2：文档版本号、交接 commit（`1be11ed` + 实施分支）、第 1 节交接结论、第 3 节业务代码状态全部与实际仓库对齐 | WORKERBUDDY_HANDOFF.md |
| — | 首轮测试 deadlock（并发 pytest 进程） | 属测试环境并发问题，按上一条按运行隔离修复；本轮证据为单进程串行运行 | g1-test-output.txt 文件头注明"串行单进程运行" |

上一轮未发现回归的项（SameSite、FLASK_DEBUG、psycopg 驱动、405 中文页、表名动态化、commit 固化、D-031）本轮保持并通过复核。

## 1. G1 完成标准核对

| 标准 | 结果 | 证据 |
|---|---|---|
| Flask 可启动 | 通过 | 第 2 节 |
| PostgreSQL schema 可初始化 | 通过 | 本地 PostgreSQL 18.6，141/161/1 |
| 基础鉴权和角色可用 | 通过 | 路由 + service 双层权限校验；三类角色登录测试齐全 |
| 健康页和错误页可用 | 通过 | /health JSON；403/404/405/500 中文页含原因与下一步 |
| 基础测试通过 | 通过 | pytest：44 passed（单元 9 + 集成 35）；Ruff 全通过 |
| 固定 commit | `363b901` | 见文件头 |

## 2. 启动命令与结果

```text
启动命令：.venv/Scripts/python -m flask --app "app:create_app()" run --port 5063
smoke test（真实服务器）：
  GET /health  -> 200 {"checks":{"app":"ok","database":"ok"},"status":"ok"}
  Set-Cookie: session=...; Secure; HttpOnly; Path=/; SameSite=Lax
  GET /me/profile（匿名）-> 302 跳转登录并保留 next
```

## 3. 数据库状态复核（本轮实测）

```text
开发库 qinghe_circle（重置后）：
  universities=141  campuses=161  platform_admins=1  students=0
残留测试库：leftover_test_dbs=0（固定旧测试库与按运行测试库均已清理）
集成测试：每次运行独立库 qinghe_circle_test_<pid>，会话结束自动删除
```

## 4. 测试命令与结果

```text
命令：.venv/Scripts/python -m pytest tests（单进程串行运行）
结果：44 passed（单元 9：tests/unit/test_auth_validation.py；
      集成 35：test_health_and_errors 5 + test_permissions 15 + test_register_and_login 15）
耗时：23.91s（本地 PostgreSQL 18.6）
Ruff：.venv/Scripts/python -m ruff check app tests -> All checks passed!
```

本轮新增测试（6 项）：
- service 层权限拒绝路径 3 项（匿名/学生拒绝、平台管理员通过，绕过路由直接调用）；
- next 端到端闭环 1 项（6 步链路，最终落点原目标页）；
- 开放重定向拒绝 1 项；
- 组织树计数 1 项。

测试证据文件：`evidence/g1-test-output.txt`（文件头含 commit/分支/环境与"串行单进程"声明）、`evidence/g1-dependencies.txt`、`evidence/g1-ruff.txt`。

## 5. 关键实现说明

- **service 权限惯例确立**：需要权限的 service 函数以 `actor` 为首参并自行校验角色；路由守卫（`login_required`/`roles_required`）只是第一道防线。该模式将带入 G2 起的所有业务 service。
- **next 闭环**：`_safe_target()` 统一校验（仅站内相对路径），身份选择/学校校区/登录/注册表单均携带隐藏 `next` 字段。
- **测试库隔离**：`qinghe_circle_test_<pid>` 按运行独立，消除并发 schema 冲突；会话结束自动清理。

## 6. 已知事项

- **手机号哈希密钥**：与 SECRET_KEY 绑定（D-033 已记录迁移路径与 G4 发布检查单要求）。当前课程环境不轮换 SECRET_KEY，无实际影响。
- 无其他已知问题。

## 7. 下一步

等待 Codex/用户对 G1（第三次提交）的审阅结论。通过后按交接书第 4 节顺序进入 G2，在 G2 再次停止提交证据。
