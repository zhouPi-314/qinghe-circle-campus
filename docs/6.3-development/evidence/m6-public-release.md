# M6 公开发布与隐私审计

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 代码基线 | `acbc2f0` |
| 许可 | 代码与原创文档 MIT；第三方媒体保留原权利 |
| 测试 | 191 passed |
| Ruff | 通过 |
| 结果 | 可以公开仓库，等待 GitHub 可见性切换后的最终核验 |

## 1. 当前文件隐私检查

- `.env.local`、`.vercel/`、虚拟环境、缓存和日志不进入 Git。
- 当前工作树未发现真实数据库连接串、R2 密钥、API Token、私钥或完整学生个人信息。
- 测试中的手机号、姓名、学号和班级均为明显虚构数据。
- 公共部署基础设施 ID 已改为占位符。
- 内部 `.workbuddy-ai/` 记忆不进入公开发布，历史中已移除。
- 种子数据不再创建固定密码管理员；首次部署使用 `tools/create_platform_admin.py`。

## 2. Git 历史隐私处理

- 公开发布前创建完整私有备份。
- 所有提交作者与提交者邮箱统一为 GitHub noreply。
- 已从历史版本清除旧课程演示口令、密码哈希盐、Cloudflare 账户 ID、Neon 项目/分支 ID、Vercel 项目/团队 ID 和 R2 公共主机。
- 为保护隐私重写提交哈希；阶段文档中的旧短哈希属于私有审阅历史，不代表公开仓库中的当前入口。

## 3. 媒体与署名

- 第三方人物、学校、公益机构、未成年人场景、用户提供图片及相关 UI 截图全部保留。
- 来源、作者、权利和修改记录见 `docs/6.2-design/assets/credits.json`、
  `work/ui-animation-proposal-20261120/sources.json` 和
  `docs/6.2-design/assets/README.md`。
- 152 张图片元数据扫描未发现 GPS 坐标；13 张图片仅保留常规作者、版权、软件或时间字段。
- 第三方媒体不纳入 MIT License，也不表示相关人物、学校或机构为项目合作、授权或背书。

## 4. 复现与贡献

- 根目录 `README.md` 说明本地启动、8 个环境变量、数据库初始化和管理员创建流程。
- 复刻或发布修改版时应保留许可声明，并注明“基于 Qinghe Circle Campus / 青禾流转，作者 zhouPi-314”。
- `CONTRIBUTING.md`、Issue 模板和 PR 模板提供参与改进入口。
- `SECURITY.md` 要求私下报告密钥、权限绕过和真实个人信息问题。

## 5. 证据

- `m6-public-release-test-output.txt`
- `m6-public-release-ruff.txt`
- `docs/6.3-development/evidence/g4-production-smoke.md`
