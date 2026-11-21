# WorkerBuddy 6.3 开发交接文档模板

> 状态：模板，尚未进入 6.3。  
> 必须先完成并批准 6.1、6.2，再由 Codex 填写本模板并生成正式 `WORKERBUDDY_HANDOFF.md`。

> AI 名称固定为 **Codex**。WorkerBuddy 不得修改课程文档、AI 提示词记录或历史阶段的 AI 标识。

## 1. 交接身份

| 项目 | 内容 |
|---|---|
| 项目 | 青禾流转（Qinghe Circle Campus） |
| 需求版本 | `[6.1 文档版本]` |
| 设计版本 | `[6.2 文档版本]` |
| 标准版本 | `[engineering-standards 版本/日期]` |
| 交接 commit | `[待填写]` |
| 计划完成日期 | `[待填写]` |

## 2. WorkerBuddy 必须先阅读

1. `AGENTS.md`
2. `docs/00-governance/engineering-standards.md`
3. `docs/00-governance/collaboration-and-quality-gates.md`
4. `docs/00-governance/glossary.md`
5. 全部冻结的 6.1、6.2 文档
6. 本交接文档的全部暂停点

未完成阅读并提交实施确认，不得写业务代码。

## 3. 本轮范围和禁止项

### 必须实现

- `[按 6.2 填写]`

### 明确不做

- 真实支付
- 真实短信
- 真实公开募捐和公益资金
- App、微信小程序
- 推荐算法、地图和物流
- 未在 6.2 出现的新模块

### 允许依赖

- `[列出锁定依赖]`

新增依赖必须先申请。

## 4. 模块和实施契约

每个模块写清：

- 模块名称和职责；
- 对外 interface；
- 允许依赖；
- 不允许调用方知道的内部实现；
- 成功结果；
- 错误模式；
- 事务和幂等规则；
- 对应测试。

不得用 pass-through Repository、Manager 或 Helper 增加层级。

## 5. 数据库契约

- `sql/schema.sql`：唯一首版数据库结构来源。
- `[表清单、关键约束和索引]`
- `[状态流转和不允许的状态跳跃]`
- `[高校/校区隔离字段与校验规则]`

WorkerBuddy 不得自行改表、改字段或新增表。

## 6. 页面与权限契约

| 路由 | 角色 | 主要动作 | 错误路径 |
|---|---|---|---|
| `[route]` | `[role]` | `[action]` | `[error]` |

关键要求：

- 表单 CSRF；
- 对象归属校验；
- 跨学校拒绝；
- 同校跨校区按设计允许；
- 错误信息给出下一步操作。

## 7. 文件与图片契约

- R2 由服务端上传。
- 单图最大 3 MB。
- 只允许 JPEG、PNG、WebP。
- 对象 key 使用随机 UUID。
- 数据库只保存对象 key。
- 不接浏览器直传和 CORS，除非另行批准。

## 8. 测试责任

WorkerBuddy：

- service 单元测试；
- PostgreSQL 集成测试；
- 路由权限与高校隔离测试；
- 四类流转和公益测试；
- R2 fake 与真实 smoke test；
- 所有测试命令和结果。

Codex：

- 独立维护 `tests/acceptance/`；
- 从需求和设计编写黑盒验收；
- 验证测试证据与实现；
- 负责最终设计、安全和发布门禁。

WorkerBuddy 不修改 `tests/acceptance/`。

## 9. 强制暂停点

### G0：开始编码前

WorkerBuddy 必须停止并提交实施确认：

```text
GATE READY: G0
已阅读标准与设计: 是
需要澄清的问题: 无/列表
计划目录与模块: 列表
计划依赖: 列表
等待: Codex/用户确认
```

收到确认后才能编写业务代码。

### G1：基础骨架完成后

完成标准：

- Flask 启动；
- PostgreSQL schema 可初始化；
- 基础鉴权和角色可用；
- 健康和错误页可用；
- 基础测试通过。

必须停下并提交：

```text
GATE READY: G1
Commit: <hash>
Startup command/result: <path>
Schema init result: <path>
Test command/result: <path>
Deviations: 无/列表
等待: Codex review
```

Codex 检查后才扩展业务模块。

### G2：第一条业务闭环完成后

完成标准：

- 一条共享借还完整链路；
- 正常与异常分支；
- 权限和高校隔离；
- service、route、model、template、tests 齐全。

必须停下并提交证据，等待 Codex 审查共享模式、状态机和接口。通过后再实现其余流转。

### G3：全功能完成后

完成标准：

- 四类物品流转；
- 公益首版三项功能；
- 单元与集成测试；
- 数据库和种子数据；
- 设计偏差清单。

必须停止新增功能和代码编辑，提交固定 commit 和测试证据，等待 Codex 系统性验收。

### G4：发布候选

Codex 完成：

- 独立验收测试；
- 设计符合性审查；
- 安全审查；
- 测试证据审查；
- 受控修复；
- 最终回归。

WorkerBuddy 按缺陷清单修复后再次停止。用户最终批准后才能部署 Production。

## 10. 遇到以下情况立即停止

- 需求或设计自相矛盾；
- 需要改表或改核心状态；
- 需要新增核心依赖；
- 发现跨学校数据泄露；
- 发现密钥泄露；
- 测试无法稳定复现；
- 同一问题连续两次修复失败。

提交到 `docs/00-governance/decision-log.md` 或缺陷记录后等待决定。

## 11. WorkerBuddy 实施确认模板

```text
项目：青禾流转
需求版本：
设计版本：
工程标准版本：
已阅读全部必读文档：是
本轮范围：
明确不做：
计划模块：
计划数据库改动：无
计划新增依赖：无/列表
发现的问题：无/列表
我理解 G1、G2、G3、G4 必须停下等待审阅：是
```

