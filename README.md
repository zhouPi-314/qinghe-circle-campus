# 青禾流转 Qinghe Circle Campus

面向高校的校园物品共享、二手流转、免费赠送、绿色回收与公益实物捐赠平台。项目使用 Flask 服务端渲染，支持多高校逻辑隔离、学生名单核验、四类流转状态机、一次性交接码、争议处理、公益回执和 R2 图片存储。

- 已部署的在线官方网站：<https://qinghe-circle-campus.vercel.app>
- Python：3.13
- 数据库：PostgreSQL 18
- 许可：代码与原创文档采用 MIT；第三方媒体保留原权利人许可，不随 MIT 重新授权

> 本项目最初作为课程作业完成，现以开源方式分享，欢迎使用、提出问题和参与改进。它是教学与工程示例，不承诺生产级 SLA，也不接收真实公益资金。


## 功能范围

| 模块 | 能力 |
|---|---|
| 身份与学校 | 学生名单核验注册、学生/公益管理员/平台管理员/校级管理员登录 |
| 物品 | 发布、筛选、详情、图片、下架与审核 |
| 流转 | 借用、出售模拟支付、赠送、回收及一次性交接码 |
| 异常 | 取消、归还、站点验收、争议和状态历史 |
| 公益 | 实物需求、捐赠、站点核验、进度、脱敏回执 |
| 管理 | 高校/校区/站点、账号、名单导入、内容审核、争议和审计 |

明确不包含真实支付、短信、邮件验证码、实名认证、公开募捐、公益资金、物流、地图、实时聊天和推荐算法。

## 如需本地复刻部署

### 1. 准备环境

需要 Python 3.13 和 PostgreSQL 18。

```powershell
git clone https://github.com/zhouPi-314/qinghe-circle-campus.git
cd qinghe-circle-campus
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env.local
```

macOS/Linux 将虚拟环境命令替换为 `source .venv/bin/activate`。

### 2. 配置 `.env.local`

| 变量 | 必填 | 说明 |
|---|---|---|
| `SECRET_KEY` | 是 | 至少 32 字符的随机值；轮换前必须阅读手机号哈希迁移说明 |
| `DATABASE_URL` | 是 | 形如 `postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require` |
| `CLOUDFLARE_ACCOUNT_ID` | 图片上传时需要 | Cloudflare 账户 ID |
| `R2_ACCESS_KEY_ID` | 图片上传时需要 | R2 Access Key ID |
| `R2_SECRET_ACCESS_KEY` | 图片上传时需要 | R2 Secret Access Key |
| `R2_BUCKET_NAME` | 图片上传时需要 | R2 Bucket 名称 |
| `R2_ENDPOINT` | 图片上传时需要 | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_PUBLIC_BASE_URL` | 图片上传时需要 | R2 公共读取域名 |

上述配置本项目未真实值提交到 Git、Issue、PR、日志或截图中。真实学生姓名、学号、手机号、名单 CSV 和公益受助对象信息同样也禁止提交。

### 3. 初始化数据库与管理员

先创建空数据库，然后在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\init_database.py
.\.venv\Scripts\python.exe tools\create_platform_admin.py
```

种子数据暂时只包含 141 所四川省的所有高校、161 条校区记录和 7 个物品分类，不包含管理员密码或真实学生名单。管理员密码由第二条命令在终端输入。

### 4. 启动

```powershell
.\.venv\Scripts\python.exe -m flask --app "app:create_app()" run --port 5063
```

打开 <http://127.0.0.1:5063>。

### 5. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

集成测试需要可创建临时数据库的 PostgreSQL 账号。R2 凭据未配置时，真实 R2 smoke test 会跳过。

## 演示顺序

1. 平台管理员登录并创建公益管理员、分配回收站点。
2. 导入虚构学生名单，学生完成注册。
3. 学生发布四类物品，另一名学生发起申请。
4. 展示申请接受、交接码、完成、归还、回收验收和争议。
5. 平台管理员创建公益项目，学生提交实物捐赠与图片。
6. 站点管理员核验捐赠并发布脱敏回执。
7. 演示高校隔离、越权 403、跨校对象 404、CSRF 和错误页。

## 部署

生产推荐 Vercel + Neon PostgreSQL + Cloudflare R2：

1. 把上述 8 个非空环境变量配置到平台 Secret 管理。
2. 在 Neon 创建数据库，执行 `sql/schema.sql` 或 `tools/init_database.py`。
3. 在公网环境运行 `tools/create_platform_admin.py` 创建独立管理员，禁止使用公开示例密码。
4. Vercel 使用仓库根目录的 Flask 入口 `main.py`。
5. 部署后验证 `/health`、登录、数据库读写、R2 上传与公网读取。

更完整的基础设施说明见 `docs/0-pre-development/07-Vercel-Neon-R2接入指南.md`。

## 安全与隐私

- 手机号以 HMAC 哈希和末四位保存，不保存可回显的完整手机号。
- 密码仅保存慢哈希，生产 Cookie 启用 `Secure`、`HttpOnly`、`SameSite=Lax`。
- 公开文本拒绝手机号、身份证号和邮箱；图片中的弱结构化隐私由管理员人工核验。
- 发现安全漏洞或泄露的凭据时，请勿公开提交 Issue，按 `SECURITY.md` 私下报告。
- 仓库不附带真实学生数据。测试中的姓名、手机号、学号和班级均为虚构示例。

## 使用、复刻与署名

你可以直接访问本项目已公网配置好的官网进行使用，也可以基于它继续开发或参与本项目开发完善。复刻、发布修改版或用于课程展示时，请：

1. 保留 `LICENSE` 中的版权与许可声明。
2. 在项目 README、About 或衍生产品说明中注明“基于 Qinghe Circle Campus / 青禾流转，作者 zhouPi-314”。
3. 不要使用“官方青禾流转”或原作者身份暗示未经授权的运营关系。
4. 自行准备数据库、对象存储、域名、通知方式和合规审查，不同复制原作者的生产密钥。

如果你的用途需要更强的网络服务条款或专利授权，可在 Apache-2.0 等许可证下重新授权你拥有权利的代码部分；第三方素材按各自许可处理。

## 贡献

欢迎提交功能建议、直接参与项目后续开发完善、可用性反馈、测试用例和 Pull Request。请先阅读：

- `CONTRIBUTING.md`：开发、测试、隐私和 PR 要求
- `SECURITY.md`：安全漏洞私下报告方式
- `THIRD_PARTY_NOTICES.md`：第三方素材与公开仓库删减说明
- `docs/README.md`：需求和设计文档索引

也欢迎在 GitHub Discussions 讨论使用场景、改进方向和愿意参与的工作。

## 已知限制

- 首版无真实支付、短信、邮件、实名认证和公开募捐。
- 无管理员自助改密页面，密码重置需要受控运维操作。
- 并发验证以线程级测试为主，未做生产级压测。
- 高校校区部分记录仍标记为 `temporary`，正式运营前需逐校核验。
- 第三方人物、学校、公益机构、未成年人场景和用户提供图片保留在仓库中用于课程与场景说明，来源记录见 `docs/6.2-design/assets/credits.json` 和 `work/ui-animation-proposal-20261120/sources.json`；这些素材不随 MIT 代码授权，也不代表相关机构、人物或活动与本项目存在合作、授权或背书。

## License

Copyright (c) 2026 zhouPi-314. Original source code and original project documentation are licensed under the MIT License. Third-party media, trademarks and institutional marks retain their own rights and are included only as attributed course-demo and scene-illustration material.
