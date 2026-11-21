# Codex G4 独立验收报告

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 代码基线 | `[private-history]` |
| 验收分支 | `codex/6.3-acceptance` / `main` |
| Production | `https://qinghe-circle-campus.vercel.app` |
| 结论 | **G4 验收通过；用户已批准发布（D-042）** |

## 1. 最终回归

- 全量测试：189 passed。
- Ruff：通过。
- PostgreSQL：本地独立临时验收库；生产 Neon PostgreSQL 18 健康检查通过。
- R2：真实上传、Edge 公网读取、删除清理通过。
- 浏览器：Microsoft Edge 桌面视口与 390px 移动视口通过。
- 证据：`g4-final-test-output.txt`、`g4-final-ruff.txt`、`g4-production-smoke.md`。

## 2. G4 受控修复

| 问题 | 修复 |
|---|---|
| 公网 `/items` 空列表返回 500 | `items/discover.html` 改用真实端点 `items.new_item`，并增加空列表渲染测试 |
| 平台概览“物品”统计显示字典方法字符串 | 模板改用 `counts['items']`，并增加统计输出断言 |
| 回收物主看不到回收申请表单 | 物品详情模板调整回收分支顺序 |
| 回收交接码显示给错误角色 | 按交付方/接收方区分待交接操作 |
| 公益回执公开页 500 | 补充 `CharityReceipt.project` 只读关系 |
| 回执项目选择 GET 表单提交 CSRF 到 URL | 删除 GET 表单中的 CSRF 隐藏字段 |
| 学生可进入空站点工作台 | `/station` 增加角色守卫 |
| 缺少 Vercel 入口 | 使用 Vercel 原生 Flask `main.py` 入口 |

每项修复均增加或复用了对应测试。

## 3. 公共门禁结果

- `/health`：200，`app=ok`、`database=ok`。
- 已登录管理员访问 `/items`、`/admin/`、内容审核、账号、公益、个人资料页：200。
- 未登录访问 `/admin`、`/items`、`/me/profile`：跳转身份选择并保留 `next`。
- 会话 Cookie：`Secure=true`、`HttpOnly=true`、`SameSite=Lax`。
- 生产数据库写：管理员原值更新“四川大学”，页面提示成功，审计新增 `org.university.update / university#1`。
- R2：临时 PNG 上传成功，Edge 公网读取 200/`image/png`，删除后返回 404。
- 平台管理员密码：已轮换为随机值，数据库保存 scrypt 哈希，`password_must_change=false`；明文未写入仓库或文档。

## 4. 已知限制

1. G4 时种子数据曾保留本地课程演示密码；M6 公开发布已移除该密码，并增加交互式管理员初始化工具。
2. 首版仍无管理员自助改密或首次登录强制改密页面；当前生产账号通过受控数据库操作完成轮换。
3. 并发验证为线程级课堂演示，不是生产级压测。
4. R2 使用 Public Development URL，适合课程展示，不等同于生产级自定义域名和长期运维方案。
5. 公益捐赠回执发放时间、高校编辑交互等已知产品偏差沿用 G3/G4 加固记录。

## 5. 发布建议

当前代码、生产部署、数据库、R2 和权限 smoke 已满足 G4 技术验收条件，用户已批准发布。项目进入 M6 发布与课程交付收尾。
