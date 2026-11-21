# G5 Production 发布与公网验证

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-22 |
| Production | `https://qinghe-circle-campus.vercel.app` |
| Git 提交 | `4a976c7` |
| Vercel Deployment | `dpl_CCyXt7is5SqvTbXMzQxVb4qxN7AM` |
| 应用状态 | G5-A/B/C 已部署 |
| 数据库 | PostgreSQL 18.6，31 张表 |
| Cloudflare | R2 可用；WAF、Bot Fight Mode 和 Rate Limiting 按 D-055 暂缓 |

## 1. 数据库迁移

迁移前只读核对：

- 27 张 public 表。
- 141 所高校、161 条校区、1 个账号、0 个物品。
- `registration_verification_requests`、`security_events`、`security_blocks`、`application_events` 均不存在。

迁移后核对：

- 31 张 public 表。
- 4 张 G5 表全部存在。
- 迁移入口使用随机令牌、常量时间比较、PostgreSQL advisory lock 和添加式 SQL。
- 迁移完成后立即撤销入口代码和 Production 令牌，最终公网入口返回 404。

## 2. 自动化回归

- 最终代码：`pytest` 286 passed。
- 临时迁移入口独立安全测试：3 passed，最终代码不包含该入口。
- `ruff check app tests`：通过。
- `pip-audit -r requirements.txt`：无已知漏洞。
- 7 份 Word：结构检查 0 问题，73 页渲染检查通过。

## 3. 公网 smoke

| 检查 | 结果 |
|---|---|
| `/health` | 200，应用和数据库均为 `ok` |
| `/auth/identity` | 200；显示“进入本校管理范围”，无“暂未开放”旧文案 |
| 未登录 `/admin/operations` | 302 跳转登录 |
| 平台管理员登录 | 成功 |
| `/admin/operations` | 200，含短信和安全事件 |
| `/admin/users` | 200 |
| 学生 `/auth/register/captcha.png` | 200、`image/png`、`Cache-Control: no-store` |
| 临时迁移入口 GET | 404 |

## 4. 部署修复

- G5 运行时依赖同步加入 `pyproject.toml`：阿里云号码认证 SDK 和 Pillow。
- 新增 `.vercelignore`，排除本地虚拟环境、worktree、QA、文档、Word 和测试，避免函数包超过 500 MB。
- Cloudflare 响应头未出现 `cf-ray`，未宣称 WAF 生效。
