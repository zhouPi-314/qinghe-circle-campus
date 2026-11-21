# 企业级登录页改版与 Edge 验收

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 页面 | `/auth/login` |
| 浏览器 | Microsoft Edge 157.0.4341.60 |
| 断点 | 1440px、768px、390px |
| 结果 | 通过 |

## 1. 设计结果

- 保留蓝白科技风格，采用企业 SaaS 双栏登录结构。
- 视觉主体改为项目专属的校园循环共享网络：轨道、流转中心、书籍、生活用品与公益捐赠节点。
- 登录表单保留原有 CSRF、`next`、输入校验、错误反馈和角色文案。
- 新增密码显示切换和仅保存账号的“记住账号”能力，不保存密码。
- 所有插画、图标和动效均由项目 HTML/CSS/JS 原创实现，没有新增外部图片、字体或依赖。
- 未改动身份选择、注册、首页或其他业务页面模板。

## 2. 自动与交互验证

- 1440、768、390 三个宽度均无横向溢出，登录表单可见。
- 密码显示切换通过：`type=password -> text`、`aria-pressed=true`、标签切换为“隐藏密码”。
- “记住账号”通过，仅将账号写入当前浏览器 `localStorage`。
- 使用虚构错误账号提交后，页面显示账号或密码错误提示，并保留账号输入。
- 键盘 Tab 顺序为品牌入口、切换身份、账号、密码、显示密码、记住账号、登录。
- 输入框与登录按钮有可见焦点；密码按钮、身份切换链接、记住账号热区均至少 44px。
- 减少动态模式下，轨道动画和交互过渡缩短到 `0.01ms`，内容完整保留。
- Edge `Runtime.exceptionThrown` 与控制台 error 均为 0。

## 3. 截图

- [桌面 1440px](login-redesign-desktop.png)
- [手机 390px](login-redesign-mobile.png)

## 4. 复现命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_register_and_login.py::TestIdentityFlow::test_login_page_has_accessible_enterprise_form
.\.venv\Scripts\python.exe -m ruff check app tests
```

素材与依赖清单见根目录 `licenses.json`。
