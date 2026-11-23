<div align="center">

# 青禾流转

### Qinghe Circle Campus

**让闲置继续流动，让资源遇见下一位需要的人。**

A Campus Circular Sharing Platform

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00)](https://www.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/tests-301%20passed-2EA44F)](tests/)
[![License](https://img.shields.io/badge/license-MIT-3DA639)](LICENSE)
[![Vercel](https://img.shields.io/badge/Vercel-deployed-000000?logo=vercel&logoColor=white)](https://qinghecircle.dpdns.org)

[**官方网站**](https://qinghecircle.dpdns.org) ·
[**项目文档**](docs/README.md) ·
[**版本更新**](https://github.com/zhouPi-314/qinghe-circle-campus/releases) ·
[**参与贡献**](CONTRIBUTING.md)

</div>

面向高校的校园物品共享、二手流转、免费赠送、绿色回收与公益实物捐赠平台。项目使用 Flask 服务端渲染，支持多高校逻辑隔离、学生名单核验、四类流转状态机、一次性交接码、争议处理、公益回执和 R2 图片存储。

> 本项目以开源方式分享，欢迎使用、提出问题和参与改进。它是校园场景的工程示例，不承诺生产级 SLA，也不接收真实公益资金。

> **当前版本状态：** `v1.1.0` 已合并并部署，包含校级管理员本校治理、图形验证码、阿里云短信认证和平台运维安全中心。公网主入口迁移到 `https://qinghecircle.dpdns.org`，Cloudflare Free WAF、默认 Vercel 入口封锁和免费收件转发已启用。代码与原创文档采用 MIT；第三方媒体保留原权利人许可，不随 MIT 重新授权。

## 项目背景

高校学生在入学、换课、毕业和搬寝等周期中会产生大量仍可使用的教材、文具、宿舍用品、体育用品和小型电子设备。群聊、公告栏和临时线下活动可以传播信息，却很难同时解决四个问题：

- 同一件物品在借用、出售、赠送和回收之间缺少清晰、互斥的状态。
- 交接依赖口头约定，申请人、时间、凭证和异常处理难以追溯。
- 多高校同时使用时，学校数据、管理员范围和公益项目必须隔离。
- 公益物资从需求、募集到接收回执缺少可核查的公开链路。

青禾流转把分散的流转行为组织为一条可搜索、可确认、可追踪的流程。系统采用多高校逻辑隔离，个人只能参与所属学校的业务；管理员按平台、学校和站点范围分工；公益首版只处理实物需求、捐赠核验和脱敏回执，不接收真实资金。

## 功能结构

| 模块 | 能力 |
|---|---|
| 身份与准入 | 学生名单核验、图形验证码、阿里云短信认证、四类身份登录、学校与校区隔离 |
| 物品与媒体 | 发布、搜索、筛选、详情、图片、上下架与内容审核 |
| 流转与交接 | 借用、出售模拟支付、赠送、回收、一次性交接码、归还与逾期 |
| 公益与回执 | 实物需求、捐赠、站点核验、募集进度、脱敏回执公示 |
| 管理与治理 | 平台全局管理、校级管理员本校组织/账号/名单/审核/争议、运维安全中心 |
| 工程与部署 | PostgreSQL 数据模型、权限测试、R2、阿里云 PNVS、Vercel + Neon 公网复刻 |

### 界面预览

| 学生发现与四类流转 | 流转详情与交接状态 |
|---|---|
| ![学生发现页](docs/6.2-design/assets/ui-list-a.png) | ![物品详情与交接状态](docs/6.2-design/assets/ui-item-detail.png) |

| 公益项目与募集进度 | 公益捐赠与站点核验 |
|---|---|
| ![公益项目](docs/6.2-design/assets/ui-charity.png) | ![公益捐赠表单](docs/6.2-design/assets/ui-donation-form.png) |

| 学生身份核验注册 | 平台管理员与名单导入 |
|---|---|
| ![学生注册与双重验证码](docs/6.3-development/evidence/g5-register.png) | ![平台管理员名单导入](docs/6.2-design/assets/ui-admin-import.png) |

| 校级管理员本校概览 | 平台管理员运维与安全 |
|---|---|
| ![校级管理员本校概览](docs/6.3-development/evidence/g5-school-admin.png) | ![平台管理员运维与安全](docs/6.3-development/evidence/g5-operations.png) |

明确不包含真实支付、邮件验证码、实名认证、公开募捐、公益资金、物流、地图、实时聊天和推荐算法。真实手机验证码使用阿里云短信认证服务。

## 平台管理员账号

公开站点不提供管理员密码查询。生产密码只保存慢哈希，无法从网页或数据库哈希反推明文。默认登录名通常是 `platform_admin`，但登录名不等于密码。

- 有 Vercel/Neon 权限时，可按 [平台管理员账号获取与恢复](docs/6.3-development/admin-access-and-recovery.md) 使用受控脚本创建一个独立恢复账号。
- 没有基础设施权限时，请通过项目所有者恢复；不要在公开 Issue 或 Discussion 中请求或发送密码。
- 当前首版没有管理员自助改密页面，密码重置属于受控运维操作。

## 如需本地复刻部署

本地完整复刻分为四层：应用、数据库、对象存储和公网平台。先打通最小版本，再按需要增加 R2 图片与 Vercel 部署。

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

最小版本只需要 Python、PostgreSQL、Flask 和数据库连接；R2、Vercel 和 Neon 都不是本地启动的强制条件。

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
| `SMS_PROVIDER` | 是 | 本地可用 `mock`，Production 必须为 `aliyun_pnvs` |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | 阿里云短信时需要 | 专用 RAM AccessKey ID |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 阿里云短信时需要 | 专用 RAM AccessKey Secret |
| `ALIYUN_PNVS_SIGN_NAME` | 阿里云短信时需要 | 系统赠送签名名称 |
| `ALIYUN_PNVS_TEMPLATE_CODE` | 阿里云短信时需要 | 登录/注册验证码模板 Code |
| `ALIYUN_PNVS_REGION_ID` | 可选 | 默认 `cn-hangzhou` |
| `TRUST_CLOUDFLARE_IP_HEADER` | Cloudflare 代理时需要 | 默认 `false` |
| `CLOUDFLARE_ORIGIN_SECRET` | 上项为 true 时必填 | Cloudflare 注入的源站共享密钥 |
| `TURNSTILE_SITE_KEY` | 可选 | 登录页 Cloudflare Turnstile 公开站点密钥 |
| `TURNSTILE_SECRET_KEY` | 与服务端验证配套 | Turnstile 私密密钥，只放在服务端 Secret |
| `PUBLIC_ALLOWED_HOSTS` | Production 入口守卫需要 | 允许进入 Production 的 Host，逗号分隔 |

上述配置真实值不得提交到 Git、Issue、PR、日志或截图中。真实学生姓名、学号、手机号、名单 CSV、短信测试号和公益受助对象信息同样禁止提交。

### 3. 初始化数据库与管理员

先创建空数据库，然后在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\init_database.py
.\.venv\Scripts\python.exe tools\create_platform_admin.py
```

种子数据暂时只包含 141 所四川省的所有高校、161 条校区记录和 7 个物品分类，不包含管理员密码或真实学生名单。管理员密码由第二条命令在终端输入。

管理员创建后会得到普通登录账号和密码哈希；系统不会保存可回显的明文密码。

### 4. 启动与首个检查

```powershell
.\.venv\Scripts\python.exe -m flask --app "app:create_app()" run --port 5063
```

打开 <http://127.0.0.1:5063>。

建议依次检查：

1. `/health` 返回应用和数据库正常。
2. 平台管理员可登录并看到平台概览。
3. 导入虚构学生名单，学生通过图形验证码和短信验证码完成注册登录；本地无云凭据时使用页面显示的 Mock 码。
4. 发布一件物品并完成一次借用或赠送闭环。
5. 未配置 R2 时，图片入口应给出明确提示，不影响文字业务。

### 5. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

集成测试需要可创建临时数据库的 PostgreSQL 账号。R2 凭据未配置时，真实 R2 smoke test 会跳过。

### 6. 复刻时建议增加的模块

| 模块 | 用途 | 是否本地必需 |
|---|---|---|
| PostgreSQL 迁移与种子 | 复现高校、校区、分类和空管理员基线 | 是 |
| 名单导入 | 用虚构 CSV 验证学号、手机号、校区匹配 | 是 |
| 四类状态机 | 验证同一物品只允许一个进行中业务 | 是 |
| 交接码与争议 | 验证取消、过期、逾期、归还和管理员处理 | 是 |
| 公益核验与回执 | 验证进度不超募和公开内容脱敏 | 是 |
| 短信认证 | Mock 自动测试 + 阿里云 PNVS 真实 smoke | 是，真实短信可选 |
| 运维安全中心 | 运行状况、错误、攻击分类和临时封禁处置 | 是 |
| Cloudflare R2 | 物品与公益图片上传、读取和删除 | 否，图片增强 |
| Vercel + Neon | 公网应用入口与托管 PostgreSQL | 否，部署增强 |

邮件验证码、支付结算和公开募捐不在当前实现范围内。真实短信使用阿里云号码认证短信认证；Cloudflare Free 已用于 R2、自定义域名 WAF、Bot Fight Mode、注册速率限制和 `contact@qinghecircle.dpdns.org` 收件转发。

## 部署

生产推荐 Vercel + Neon PostgreSQL + Cloudflare R2：

1. 把数据库、R2 和阿里云短信相关环境变量配置到平台 Secret 管理；Production 禁止 `SMS_PROVIDER=mock`。
2. 在 Neon 创建数据库，执行 `sql/schema.sql` 或 `tools/init_database.py`。
3. 在公网环境运行 `tools/create_platform_admin.py` 创建独立管理员，禁止使用公开示例密码。
4. Vercel 使用仓库根目录的 Flask 入口 `main.py`。
5. 部署后验证 `/health`、登录、数据库读写、R2 上传与公网读取。
6. 先执行添加式数据库迁移，再部署新应用版本；阿里云短信先使用受控测试手机 smoke。
7. 自定义域名通过 Cloudflare Proxied DNS 和 Full (strict) 接入；Cloudflare 请求头转换规则注入源站共享密钥，应用只接受白名单 Host。默认 `vercel.app` Production 入口返回应用 404。

更完整的基础设施说明见 `docs/0-pre-development/07-Vercel-Neon-R2接入指南.md`。

## 安全与隐私

- 手机号以 HMAC 哈希和末四位保存，不保存可回显的完整手机号。
- 阿里云短信验证码不进入数据库；应用只保存挑战状态、HMAC 标识和 Provider 流水信息。
- 同一 IP 10 分钟内第 9 次注册短信请求会触发 15 分钟临时阻断和分类安全事件。
- 密码仅保存慢哈希，生产 Cookie 启用 `Secure`、`HttpOnly`、`SameSite=Lax`。
- 登录页在配置 Turnstile 密钥后使用 Cloudflare 官方组件和服务端校验；未配置时使用自托管图片验证码。
- 公开文本拒绝手机号、身份证号和邮箱；图片中的弱结构化隐私由管理员人工核验。
- 发现安全漏洞或泄露的凭据时，请勿公开提交 Issue，按 `SECURITY.md` 私下报告。
- 仓库不附带真实学生数据。测试中的姓名、手机号、学号和班级均为虚构示例。

## 使用、复刻与署名

你可以直接访问本项目已公网配置好的官网进行使用，也可以基于它继续开发或参与本项目开发完善。复刻或发布修改版时，请：

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

- 首版无真实支付、邮件验证码、实名认证和公开募捐。
- 图形验证码是项目自托管方案，不等同于商业 OCR 抗性验证码。
- 无管理员自助改密页面，密码重置需要受控运维操作。
- Cloudflare Free 自带的速率限制只有一条规则、10 秒窗口；长窗口频控仍由应用层承担。
- 并发验证以线程级测试为主，未做生产级压测。
- 高校校区部分记录仍标记为 `temporary`，正式运营前需逐校核验。
- 第三方人物、学校、公益机构、未成年人场景和用户提供图片保留在仓库中用于场景说明，来源记录见 `docs/6.2-design/assets/credits.json` 和 `work/ui-animation-proposal-20261120/sources.json`；这些素材不随 MIT 代码授权，也不代表相关机构、人物或活动与本项目存在合作、授权或背书。

## License

Copyright (c) 2026 zhouPi-314. Original source code and original project documentation are licensed under the MIT License. Third-party media, trademarks and institutional marks retain their own rights and are included only as attributed scene-illustration material.
