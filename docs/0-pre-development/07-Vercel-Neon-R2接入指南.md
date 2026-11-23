# Vercel + Neon + Cloudflare R2 接入指南

| 项目 | 内容 |
|---|---|
| 方案 | Vercel + Neon PostgreSQL + Cloudflare R2 |
| 文档版本 | 1.0 |
| 日期 | 2026-11-19 |
| 结论 | 可行，适合作为“青禾流转”的公网展示方案 |

## 1. 可行性结论

该组合可行：

- Vercel 运行 Flask/WSGI 应用和 Jinja2 模板。
- Neon 提供 PostgreSQL 数据库。
- Cloudflare R2 通过 S3-compatible API 提供图片和头像存储。
- 本地 PostgreSQL 18 和 Neon PostgreSQL 使用同一种数据库技术，减少 SQL 方言差异。
- 开发数据量远低于 Neon 免费层的 1 GB。
- 图片总量低于 R2 免费层 10 GB 时，通常不会产生存储费用。

但 R2 不是 Vercel 的内部存储绑定。Vercel 应用必须使用 S3 凭据访问 R2，因此确实需要：

- Cloudflare Account ID。
- R2 Access Key ID。
- R2 Secret Access Key。
- R2 Bucket 名称。
- R2 Endpoint。
- R2 公共访问域名。

## 2. 我能完成和不能完成的部分

### 2.1 我能完成

- 创建 Flask/Vercel 应用入口和配置文件。
- 创建 PostgreSQL 数据库模型和初始化 SQL。
- 配置 SQLAlchemy 使用 `psycopg` 连接 Neon。
- 编写物品图片和头像的 R2 上传、校验、删除和 URL 生成逻辑。
- 编写 `.env.example`，列出环境变量名称，不包含真实密钥。
- 用 `boto3` 连接 R2 的 S3-compatible API。
- 编写 R2 连接自检脚本；密钥不会打印到日志。
- 编写 Vercel 部署配置。
- 在你完成登录后执行本地启动、数据库迁移测试和部署命令。
- 执行图片上传、公开读取、权限隔离和失败恢复测试。

### 2.2 只能由你完成

- 注册/登录 Vercel、Neon 和 Cloudflare。
- 同意各平台服务条款。
- 创建 Neon 项目和 R2 存储桶。
- 决定是否给 Cloudflare R2 绑定支付方式。
- 创建 R2 API Token。
- 在 Vercel Dashboard 或本机 `.env` 中填写密钥。
- 完成 GitHub 授权、邮箱验证或人机验证。

不要通过聊天窗口发送数据库密码、R2 Secret Access Key、Vercel Token 或其他密钥。正确做法是把它们写入本机未提交的 `.env.local`，或在 Vercel 控制台中手动填写。

## 3. 最终需要的环境变量

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
SECRET_KEY=由本地随机生成

CLOUDFLARE_ACCOUNT_ID=Cloudflare账户ID
R2_ACCESS_KEY_ID=R2访问密钥ID
R2_SECRET_ACCESS_KEY=R2秘密访问密钥
R2_BUCKET_NAME=qinghe-circle-campus
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_PUBLIC_BASE_URL=https://公开访问域名
```

其中：

- `.env.example` 只保存变量名和占位符，可提交到 GitHub。
- `.env.local` 保存真实值，必须加入 `.gitignore`。
- Vercel 生产环境变量在 Project Settings 中填写。

## 4. 注册 Vercel

官方网址：

- https://vercel.com/signup
- https://vercel.com/docs/getting-started-with-vercel

### 4.1 操作步骤

1. 打开 Vercel 注册页。
2. 点击 **Sign Up / 注册**。
3. 选择 **Continue with GitHub / 使用 GitHub 继续**。  
   如果以后要把 GitHub 仓库自动部署到 Vercel，这是最省配置的方式。
4. 在 GitHub 授权页点击 **Authorize Vercel / 授权 Vercel**。
5. 选择 **Hobby / 免费版**。
6. 进入 Dashboard 后确认邮箱已验证。

### 4.2 之后要完成

- 点击 **Add New / 新建**。
- 选择 **Project / 项目**。
- 选择 **Import Git Repository / 导入 Git 仓库**。
- 授权 GitHub 仓库 `qinghe-circle-campus`。
- 如果页面显示 **Application Preset: Other / 应用预设：其他**，暂时保持 Other；等项目包含 `requirements.txt` 和 Flask 入口后，Vercel 会重新识别。不要为了一个可能不存在的 Flask 预设阻塞项目导入。
- 在 **Environment Variables / 环境变量** 中填写 `DATABASE_URL`、R2 变量和 `SECRET_KEY`。
- 点击 **Deploy / 部署**。

如果数据库和 R2 尚未创建：

- Environment Variables 保持空白。
- 不要先点击 Deploy。
- 完成 Neon 和 R2 配置后再回到 Vercel 填写。

如果使用 CLI：

```powershell
npm i -g vercel
vercel login
vercel
vercel --prod
```

`vercel login` 需要你完成浏览器登录或邮箱确认，之后我可以继续执行后续命令。

## 5. 注册 Neon

官方网址：

- https://neon.com/docs/get-started/signing-up
- https://console.neon.tech/
- https://neon.com/docs/get-started/connect-neon

### 5.1 注册

1. 打开 Neon 控制台或文档中的 **Sign up / 注册**。
2. 选择 GitHub、Google 或邮箱注册。
3. 进入 Console。

### 5.2 创建项目

1. 点击 **Create project / 创建项目**。
2. **Project name / 项目名称** 填 `qinghe-circle-campus`。
3. **Postgres version / PostgreSQL 版本** 使用控制台当前默认稳定版本。
4. 选择可用区。优先选择 **AWS Asia Pacific (Singapore) / AWS 亚太地区（新加坡）**，并把 Vercel Function 配置为 `sin1`（新加坡）。如果该区域不可用，再选择 **AWS US East 2 (Ohio)**，并保持 Vercel 默认 `iad1`。
5. 点击 **Create / 创建**。

### 5.3 获取连接字符串

1. 在 Console 左侧或顶部点击 **Connect / 连接**。
2. 选择 production 分支、数据库和 role。
3. 勾选 **Connection pooling / 连接池**。
4. 复制以 `postgresql://` 开头的连接字符串。
5. 不要直接把密码发到聊天。把连接字符串写入本机 `.env.local`，或在 Vercel **Environment Variables / 环境变量** 页面填写。

Python 连接时使用：

```text
postgresql+psycopg://...
```

而不是直接使用未加驱动前缀的 URL。

## 6. Cloudflare R2 配置

官方网址：

- R2 控制台：https://dash.cloudflare.com/?to=/:account/r2
- R2 入门：https://developers.cloudflare.com/r2/get-started/
- R2 API Token：https://developers.cloudflare.com/r2/api/tokens/
- R2 Public Bucket：https://developers.cloudflare.com/r2/buckets/public-buckets/

### 6.1 激活 R2

1. 登录 Cloudflare Dashboard。
2. 在左侧选择 **R2 Object Storage / R2 对象存储**。
3. 如果是第一次使用，点击 **Enable R2 / 启用 R2** 或 **Purchase R2 / 购买 R2**。
4. 按控制台提示完成 R2 开通。

重要：

- R2 有每月免费额度，但 Cloudflare 当前文档写明，创建 R2 API Token 前必须先 purchase R2。
- 这通常意味着需要添加支付方式或完成 R2 订阅激活。
- 免费额度内通常不会产生用量费用，但仍需以 Cloudflare 控制台当前显示为准。
- 如果不愿意绑定支付方式，改用 Vercel Blob 可以跳过 R2。

### 6.2 创建存储桶

1. 进入 **R2 Object Storage / R2 对象存储**。
2. 点击 **Create bucket / 创建存储桶**。
3. **Bucket name / 存储桶名称** 填 `qinghe-circle-campus`。
4. **Location / 位置** 选择 **Automatic / 自动**。
5. **Specify jurisdiction / 指定司法辖区** 不选，除非学校有明确的数据驻留要求。
6. **Default Storage Class / 默认存储类别** 选择 **Standard / 标准**。
7. **Infrequent Access / 不频繁访问** 不选；物品图片和头像会被反复读取。
8. 点击 **Create bucket / 创建存储桶**。

### 6.3 开启公共读取

项目展示建议：

1. 打开刚创建的 bucket。
2. 进入 **Settings / 设置**。
3. 找到 **Public access / 公共访问**。
4. 选择 **R2.dev subdomain / R2.dev 子域**。
5. 点击 **Allow Access / 允许访问** 或 **Enable / 启用**。
6. 复制生成的 `https://...r2.dev` 地址，作为 `R2_PUBLIC_BASE_URL`。

说明：

- `r2.dev` 是开发/非生产用公共地址。
- 项目展示足够。
- 正式公开运营应使用 Cloudflare 自定义域名，并配置缓存、WAF 和访问策略。

### 6.4 创建 S3 API Token

1. 回到 **R2 Object Storage / R2 对象存储** 的 Overview。
2. 在 **Account Details / 账户详情** 中找到 **API Tokens / API 令牌**。
3. 点击旁边的 **Manage / 管理**。
4. 选择 **Create Account API token / 创建账户 API 令牌**。
5. **Token name / 令牌名称** 填 `qinghe-circle-campus-upload`。
6. **Permissions / 权限** 选择 **Object Read & Write / 对象读取和写入**。
7. **Specify bucket / 指定存储桶** 选择 `qinghe-circle-campus`。
8. 点击 **Create Account API Token / 创建账户 API 令牌**。
9. 复制并保存：
   - **Access Key ID / 访问密钥 ID**
   - **Secret Access Key / 秘密访问密钥**
   - Cloudflare **Account ID / 账户 ID**

Secret Access Key 只显示一次，关闭页面后无法再次查看。不要发到聊天中。

### 6.5 配置 Endpoint

普通 R2 bucket 的 S3 Endpoint 为：

```text
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

如果创建时选择了专门 jurisdiction，则使用控制台给出的对应地区 endpoint。

## 7. R2 上传实现方式

首版为减少代码和跨域配置，建议采用服务端上传：

```text
浏览器表单
→ Vercel Flask
→ 校验类型、大小和用户权限
→ boto3 上传到 R2
→ 数据库保存对象 key
```

限制：

- 单张图片限制 3 MB。
- 只允许 JPEG、PNG、WebP。
- 不接受 SVG、HTML、可执行文件。
- 文件名使用随机 UUID，不直接使用用户原始文件名。
- 数据库只保存对象 key，不保存 Vercel 临时路径。

不采用“浏览器直传 R2”作为首版方案，因为直传还需要：

- R2 CORS。
- 预签名 URL。
- 前端上传进度和重试。
- 更复杂的权限校验。

服务端上传会让 Vercel Function 接收图片，因此必须小于 Vercel 约 4.5 MB 的请求体限制。3 MB 限制留有安全余量。

## 8. 我需要你完成的最小操作

1. 注册/登录 Vercel。
2. 注册/登录 Neon，创建 `qinghe-circle-campus` 项目并复制 pooled connection string。
3. 在 Cloudflare 中开通 R2，创建 bucket 和只限该 bucket 的 Object Read & Write Token。
4. 在 Vercel Project Settings 的 **Environment Variables / 环境变量** 中填写变量。
5. 完成后只告诉我“云资源已配置”，不要把密钥值发给我。

之后我可以执行：

- 检查连接配置是否齐全。
- 初始化 Neon 数据库。
- 运行本地测试。
- 部署 Vercel。
- 上传一张测试图片到 R2。
- 验证公网读取 URL。
- 记录失败状态并修复代码。

## 9. 费用判断

- Vercel Hobby：在免费额度内为 0。
- Neon Free：在免费额度内为 0，不需要信用卡。
- Cloudflare R2：有每月免费额度，但开通 R2 和 API Token 可能需要支付方式或订阅激活。
- 如果开发期间只上传少量图片，R2 用量通常远低于 10 GB 免费存储额度。

## 10. 不推荐现在就做的操作

- 不要创建真实学生名单。
- 不要把真实手机号导入 Neon。
- 不要把 Cloudflare API Token 写成 GitHub Actions 明文变量。
- 不要在本地 `.env.local` 之外保存 R2 Secret Access Key。
- 不要在支付、短信和公益资金仍为模拟时发布生产级公开链接。
