# 发布后界面一致性与主题切换验收

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-21 |
| 决策 | D-044、D-045、D-046、D-047、D-048、D-049、D-050 |
| 浏览器 | Microsoft Edge 157.0.4341.60 |
| 范围 | 登录、身份切换、浅深主题、首页与工作区页面 |
| 结论 | 通过；全量回归 195 passed，Ruff 通过，Edge 控制台 0 error |

## 1. 实施结果

- 新增 `tokens.css`，业务页面与登录页共用校园蓝、雾白、禾绿和语义状态令牌。
- D-045 按参考图将主色校准为 `#0B63F6`，并恢复登录主视觉下方的蓝色双环。
- D-046 将官方入口改为未选身份直接提示，并把身份切换改为单选项原地更新。
- D-047 将身份单选实时同步到服务端会话，学生校区与注册入口会等待同步后再跳转。
- D-048 仅重做学校与校区选择页，新增校园坐标网络双栏布局和原创路径动画。
- D-049 将注册页改为身份核验双栏动画，并移除校区页左侧步骤式文案。
- 注册页左侧不显示具体学校、校区或测试校名，真实范围只保留在右侧业务表单。
- D-050 在学生未绑定学校校区时拦截注册跳转，并原位提示“请先选择学校和校区”。
- 新增浅色/深色主题切换；主题写入 `localStorage`，并在 React 之外的无框架 Jinja 页面刷新后保持。
- 登录页先按视口预置主题，避免刷新时先显示错误配色。
- 登录页右上角新增“切换身份”面板；选择后沿用既有身份、学校校区、登录与 `next` 回跳流程。
- 身份面板不再跳转旧身份卡片；选中后角色标签、字段文案、账号说明和登录表单即时更新。
- 首页改为校园循环工作区；其他页面通过共享页眉、卡片、表单、表格、状态标签和物品卡统一视觉。
- 登录页桌面布局按视口高度压缩；1867×933 与 1366×768 均无需纵向滚动即可看到完整表单。
- 手机端导航改为自然换行，登录表单与身份面板保持单列。
- 桌面登录页隐藏页面滚动条；1867×933 与 1366×768 均满足 `scrollHeight === innerHeight`。
- 未新增第三方依赖、外链字体、远程图片或商业素材。
- `licenses.json` 已扩展到全站 UI、主题脚本和原创 SVG；第三方素材与既有依赖记录未删除。

## 2. 自动验收

```text
.\.venv\Scripts\python.exe -m pytest
195 passed in 137.66s

.\.venv\Scripts\python.exe -m ruff check app tests
All checks passed!
```

Edge 自动检查覆盖：

- 主色计算值为 `#0B63F6`，登录下方前后双环均保持蓝色通道占优。
- 身份面板展开、视口边界、角色切换后表单与角色标签同步。
- 浅色/深色主题切换、刷新持久化、控制台无错误。
- 登录页 1867×933 与 1366×768 均满足 `scrollHeight === innerHeight`。
- 1440、768、390 px 无横向溢出；移动端可交互控件达到 44 px 目标。
- 首页、物品发现、发布表单、物品详情、资料、申请、通知、公益项目、全部平台管理页、站点工作台、回收验收、捐赠核验、回执登记和公益项目创建页均正常渲染。
- 表单字段具备可见标签；测试账号均为临时数据库中的虚构数据。
- 本轮 Edge 检查共 81 项，全部通过，控制台 error 与 warning 均为 0。

完整机器结果见 [ui-consistency-browser-report.json](ui-consistency-browser-report.json)。

## 3. 截图

- [未选择身份入口 1867×933](ui-consistency-login-unselected-1867x933.png)
- [身份选择后 1867×933](ui-consistency-login-selected-1867x933.png)
- [登录页身份面板](ui-consistency-identity-panel-1867x933.png)
- [登录页深色 1366×768](ui-consistency-login-dark-1366x768.png)
- [学生注册防呆提示](ui-consistency-login-register-guard-1867x933.png)
- [学校与校区选择页 1867×933](ui-consistency-student-context-1867x933.png)
- [学校与校区选择页深色](ui-consistency-student-context-dark-1867x933.png)
- [学校与校区选择页 1366×768](ui-consistency-student-context-1366x768.png)
- [学校与校区选择页手机](ui-consistency-student-context-390x844.png)
- [学生注册页 1867×933](ui-consistency-register-1867x933.png)
- [学生注册页深色](ui-consistency-register-dark-1867x933.png)
- [学生注册页 1366×768](ui-consistency-register-1366x768.png)
- [学生注册页手机](ui-consistency-register-390x844.png)
- [首页浅色 1440×1000](ui-consistency-home-light-1440x1000.png)
- [首页深色 1867×933](ui-consistency-home-dark-1867x933.png)
- [首页手机 390×844](ui-consistency-home-light-390x844.png)
- [学生发布物品表单](ui-consistency-student-item-form-1440x1000.png)
- [站点工作台](ui-consistency-station-workbench-1440x1000.png)

## 4. 未覆盖与风险

- 自动检查使用临时 PostgreSQL 数据库与虚构账号，没有向真实账户提交凭据。
- 未做屏幕阅读器人工朗读测试；已检查原生语义、可见标签、键盘焦点和触摸目标。
- 深色主题不改变照片内容；未来新增图片或第三方组件时仍需分别检查浅色和深色对比度。
