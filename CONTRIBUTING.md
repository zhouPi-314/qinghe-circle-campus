# 参与贡献

感谢你关注青禾流转。欢迎提交 Bug、功能建议、可用性反馈和 Pull Request。

开放式讨论可进入 GitHub Discussions；可复现缺陷和明确功能范围使用 Issues。

## 开始前

1. 先搜索已有 Issue，避免重复。
2. 功能变更先说明使用场景、范围和不做什么。
3. 安全漏洞、真实个人信息和泄露凭据不要公开提交，按 `SECURITY.md` 报告。
4. 提交代码即表示你同意按项目 MIT License 发布你拥有权利的贡献。

## 开发流程

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env.local
.\.venv\Scripts\python.exe tools\init_database.py
.\.venv\Scripts\python.exe tools\create_platform_admin.py
.\.venv\Scripts\python.exe -m pytest
```

保持现有分层：`route -> service -> model/database`。路由不直接查询业务表，模板不判断核心业务状态，权限和事务规则在 service 中执行。

## 隐私规则

- 不提交真实姓名、学号、手机号、身份证号、住址、名单 CSV、聊天记录或清晰个人人脸。
- 测试数据必须明显虚构，不得使用真实同学信息。
- 不提交 `.env.local`、数据库连接串、R2 密钥、Token、Cookie 或部署日志中的敏感值。
- 图片和视频上传前确认版权、肖像权和再分发许可。

## Pull Request

PR 请包含：

- 解决的问题与明确范围；
- 权限、隐私和高校隔离影响；
- 测试命令与结果；
- 数据库或接口变化说明；
- 新增素材的来源和许可。

提交前至少运行：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
git diff --check
```

讨论请保持具体、友善，并围绕用户价值和可验证证据。
