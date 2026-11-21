# G4 公网 Smoke Test 证据

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 代码 commit | `4ad517d` |
| Production URL | `https://qinghe-circle-campus.vercel.app` |
| 浏览器 | Microsoft Edge 157.0.4341.60 |
| 环境 | Vercel Production + Neon PostgreSQL 18 + Cloudflare R2 |
| 结果 | 通过 |

## 1. 页面与权限

| 检查 | 结果 |
|---|---|
| Vercel Deployment | `success / Deployment has completed` |
| `/health` | 200，`{"checks":{"app":"ok","database":"ok"},"status":"ok"}` |
| `/items` | 200；空列表提示与“发布第一件物品”链接正常 |
| `/admin/`、`/admin/users`、`/admin/moderation` | 200 |
| `/charity`、`/me/requests`、`/me/profile` | 200 |
| `/static/css/style.css` | 200 |
| 未登录 `/admin`、`/items`、`/me/profile` | 跳转 `/auth/identity?next=...` |
| 会话 Cookie | `Secure`、`HttpOnly`、`SameSite=Lax` |

截图：

- [平台概览桌面视口](g4-prod-admin-desktop.png)
- [物品发现 390px 移动视口](g4-prod-items-mobile.png)

## 2. 数据库读写

1. 通过生产管理员页面读取 141 所高校、161 个校区、1 个账号。
2. 对“四川大学”提交当前名称、城市和 active 状态。
3. 页面返回“高校信息已更新”。
4. 审计页新增：`org.university.update / university#1`。
5. 高校展示值与操作前一致，没有新增测试业务对象。

## 3. R2

1. 使用唯一 key 上传 68 字节 PNG。
2. Edge 打开 Public Development URL，返回 200、`image/png`、1×1 图片。
3. 删除对象。
4. 再次访问同一 URL 返回 404。

## 4. 管理员凭据

- 生产 `platform_admin` 的密码已轮换为随机值。
- 数据库仅保存 scrypt 哈希，查询结果为 `status=active`、`password_must_change=f`、`uses_scrypt=t`。
- 明文只保存在本机被 Git 忽略的 `.env.local`，未写入本报告、日志或仓库。

## 5. 复核命令

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

结果见 `g4-final-test-output.txt` 与 `g4-final-ruff.txt`。
