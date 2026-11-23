# 发布后界面与交付维护记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 对应决策 | D-052、D-053 |
| 当前状态 | 文案、截图、README 和验证码方案已完成；验证码代码等待用户选择方案 |
| 回归结果 | 195 passed |
| 静态检查 | `ruff check app tests` 通过 |
| 公网健康检查 | `https://qinghe-circle-campus.vercel.app/health` 返回 200，应用与数据库均为 `ok` |

## 1. 已完成修改

- “公益管理员（回收）”统一为“公益管理员”。
- “校级管理员（预留）”统一为“校级管理员”；管理功能暂未开放的事实保留。
- 学校选择页移除输入框下方的可见提示：“输入单字或连续关键字，实时匹配校名与城市。”
- 保留一个仅辅助技术读取的搜索说明，避免移除提示后破坏无障碍描述。
- 更新身份选择、学校校区、学生注册、三类管理员登录和公益管理员工作台截图。
- README 增加项目背景、六模块能力、界面预览和完整本地复刻说明。
- README 项目背景只说明校园场景、技术问题与当前能力。
- 新增平台管理员账号获取与恢复说明，不包含任何密码或密钥。
- 新增注册验证码可行性、技术替代、成本、合规风险和分工计划。
- 同步更新需求与设计文档。

## 2. 验证证据

```text
.\.venv\Scripts\python.exe -m pytest
195 passed in 137.43s

.\.venv\Scripts\python.exe -m ruff check app tests
All checks passed!
```

文档结构检查结果：

- 需求与设计文档未出现旧角色名称或已移除的学校搜索提示。

当前界面证据：

- `docs/6.2-design/assets/ui-role-select.png`
- `docs/6.2-design/assets/ui-school-campus.png`
- `docs/6.2-design/assets/ui-register.png`
- `docs/6.2-design/assets/ui-login-station.png`
- `docs/6.2-design/assets/ui-login-university-admin.png`
- `docs/6.2-design/assets/ui-login-platform.png`
- `docs/6.2-design/assets/ui-station-dashboard.png`

## 3. 发布结果

- GitHub `main` 已推送提交 `1c6d125`。
- Vercel 已自动部署该提交，Production `/health` 返回应用与数据库均为 `ok`。
- 公网身份切换验证显示“公益管理员”“校级管理员”；学校选择页不再显示“实时匹配校名与城市”，搜索框仍保留“输入校名或城市关键字”。

## 4. 未完成与边界

- 图形验证码和手机号验证码尚未写入代码，等待用户选择“项目模拟版 / 真实短信版 / 仅加固版”。
- 真实短信涉及实名认证、签名和模板审核、按条计费、短信轰炸防护与隐私告知，不能仅用页面输入框替代。
- 历史决策记录和浏览器审计 JSON 保留当时名称；当前代码、规范、README、截图和设计文档使用新名称。
