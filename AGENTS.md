# 青禾流转项目协作规则

本文件是当前仓库的统一下游入口。Codex、WorkerBuddy 和人工维护者都必须先遵守本文件，再阅读它指向的规范。

## 当前阶段

- 项目名称：青禾流转（Qinghe Circle Campus）
- 当前状态：G4 已由用户批准通过并授权发布（D-042）；项目进入 M6 发布与课程交付收尾，Codex 负责 README、复现说明、证据索引、仓库清理和演示材料，WorkerBuddy 保持停止
- G1 通过前不得进入 G2 业务编码；各门禁停止点见 `docs/00-governance/collaboration-and-quality-gates.md`

## 强制阅读顺序

开始 6.1 前阅读：

1. `docs/0-pre-development/01-问题定义.md`
2. `docs/0-pre-development/02-可行性研究报告.md`
3. `docs/0-pre-development/03-项目开发计划.md`
4. `docs/0-pre-development/04-已确认范围与约束.md`

开始 6.3 编码前，WorkerBuddy 还必须完整阅读：

1. `docs/00-governance/engineering-standards.md`
2. `docs/00-governance/collaboration-and-quality-gates.md`
3. `docs/00-governance/glossary.md`
4. 全部已冻结的 6.1、6.2 文档
5. `docs/6.3-development/handoff/WORKERBUDDY_HANDOFF.md`

## 唯一标准

- 技术标准只以 `docs/00-governance/engineering-standards.md` 为准。
- 业务术语只以 `docs/00-governance/glossary.md` 为准。
- 阶段职责与暂停点只以 `docs/00-governance/collaboration-and-quality-gates.md` 为准。
- 范围、接口、数据库或业务规则变更必须记录在 `docs/00-governance/decision-log.md`。
- WorkerBuddy 不建立第二套规范，不另建平行目录，不以自己的偏好覆盖仓库规范。

## 固定 AI 标识

- 课程文档和 AI 交互记录中的 AI 名称统一为 `Codex`。
- 该名称在 6.1、6.2、6.3 和历史文档中保持一致。
- WorkerBuddy 只能作为后续实现执行者，不能修改 AI 名称、历史提示词或 Codex 编写的阶段文档。

## 写入权

- 6.1、6.2：Codex 编写，用户批准。
- 6.3：同一时间只允许一个 Agent 修改业务代码。
- WorkerBuddy 开发期间：WorkerBuddy 是编码写入者。
- Codex 验收期间：WorkerBuddy 停止编辑，Codex 可进行受控修复。
- 用户是范围变更和最终发布的批准者。

## 强制暂停

WorkerBuddy 到达以下门禁时必须停止继续开发并等待审阅：

1. **G0 交接确认**：编码开始前。
2. **G1 基础骨架**：应用可启动、数据库可初始化、基础权限生效后。
3. **G2 第一条业务闭环**：第一条完整流转链及其测试完成后。
4. **G3 全功能完成**：四类物品流转和公益首版完成后。
5. **G4 发布候选**：Codex 验收、修复和最终回归完成后。

门禁的具体完成条件和停止指令见 `collaboration-and-quality-gates.md` 和 WorkerBuddy 交接文档。

## 安全底线

- 真实密钥只放在 `.env.local`、Vercel Secrets 或平台密钥管理中。
- 不提交密码、验证码、数据库连接串、R2 Access Key、R2 Secret、API Token。
- 不在日志或测试报告中输出学生手机号、密码和完整连接串。
- 真实支付、短信、公开募捐和公益资金不进入当前版本。

