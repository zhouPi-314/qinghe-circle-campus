# 校级管理员与注册短信验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为校级管理员提供严格限制在本校范围内的日常管理能力，并为学生注册增加图形验证码、阿里云短信验证码和一次性服务端验证闭环。

**Architecture:** 继续扩展现有 `route → service → model/database`，不新增平行后台。校级权限通过 `CurrentUser.is_university_admin` 和统一高校边界校验下沉到现有 service；短信通过可替换的 `SmsSender` Provider 注入，测试使用 Mock，生产使用阿里云短信认证 V2 SDK。

**Tech Stack:** Python 3.13、Flask 3.1、SQLAlchemy 2、PostgreSQL 18、Pillow 13、阿里云号码认证 Dypnsapi Python SDK 2.0、pytest、Ruff。

**Spec:** `docs/6.3-development/g5-university-admin-and-registration-sms-design.md`

## G5-0 Approval

User approved the scope on 2026-11-21 in D-054. Aliyun SMS Authentication (PNVS) is the selected production provider; standard SMS `SendSms` is not used for this personal account.

## Global Constraints

- 同一时间只有 项目维护者 修改 `app/`、`tests/unit/`、`tests/integration/` 和 `sql/schema.sql`；项目维护者 只维护方案、验收测试和受控修复。
- 冻结业务顺序：先完成并验收 G5-A 校级管理员，再开始 G5-B 短信；G5-B 未通过不得发布 Production。
- `university_admin` 只能使用自己的 `university_id`；任何表单高校 ID 都必须与 actor 对比。
- 跨校越权、停用账号、无授权站点、错误验证码、过期验证码、重发过快、短信服务异常都必须在 service 层拒绝。
- 不保存手机号明文、短信验证码明文、AccessKey、Secret 或完整请求 IP。
- 校级管理员的有效范围同时要求 `actor.university_id` 相同且该高校状态为 `active`。
- 自动化测试不访问阿里云；真实短信 smoke test 只向维护者控制的手机号发送。
- 数据库改动使用添加式迁移，不删除或重命名既有表和字段。
- 新依赖仅允许 `alibabacloud_dypnsapi20170525==2.0.0` 和 `pillow==13.0.0`。
- 短信请求 60 秒冷却必须同时由前端倒计时和服务端时间比较实现。
- 自动 IP 封禁只作用于注册与短信端点，采用临时封禁和人工复核，避免共享校园 NAT 永久误伤。
- Cloudflare Free 只有在自有域名代理通过 Cloudflare 时才可宣称生效；`vercel.app` 不能直接套 Cloudflare WAF。

## Review Focus

1. 校级管理员在表单中伪造其他 `university_id`：必须被 service 层拒绝。
2. 校级管理员删除自己或提升角色：必须没有可用接口，直接 service 调用也拒绝。
3. 并发重发短信：同一名单记录只能有一条有效挑战，重发额度不能被并发穿透。
4. 图形验证码或短信验证码重放：成功消费后不能再次注册。
5. 阿里云超时、额度不足或配置缺失：不能静默转 Mock，也不能创建学生账号。
6. 同一 IP 高频请求触发临时封禁：只阻断注册/短信端点，事件可分类、可解除、可标误报，不能误封全站。

---

### Task 1: 校级管理员权限快照与范围守卫

**Files:**
- Modify: `app/core/permissions.py`
- Create: `tests/unit/test_school_scope.py`
- Create: `tests/integration/test_university_admin.py`

**Interfaces:**
- Produces: `CurrentUser.is_university_admin: bool`
- Produces: `ensure_actor_university(actor: CurrentUser, target_university_id: int) -> int`
- Produces: `is_university_manager(actor: CurrentUser) -> bool`

- [ ] **Step 1: Write failing unit tests**

```python
def test_university_admin_scope_accepts_same_school(actor):
    assert ensure_actor_university(actor, actor.university_id) == actor.university_id

def test_university_admin_scope_rejects_other_school(actor):
    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(actor, actor.university_id + 1)
```

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_school_scope.py -v`

Expected: FAIL because `is_university_admin` and `ensure_actor_university` do not exist.

- [ ] **Step 3: Implement permission helpers**

`ensure_actor_university` accepts `platform_admin` as global, accepts `university_admin` only when actor and target IDs match, and rejects `None`, students, station managers and cross-school targets.

- [ ] **Step 4: Add integration assertions**

Create a school admin for university A and a second university B. Assert own-school access succeeds and every B object access raises `PermissionDeniedError`.

Also set school A to `inactive` and assert the same actor is denied until the university is re-enabled.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_school_scope.py tests\integration\test_university_admin.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/core/permissions.py tests/unit/test_school_scope.py tests/integration/test_university_admin.py
git commit -m "feat: add university admin scope guard"
```

### Task 2: 本校概览与组织服务

**Files:**
- Modify: `app/services/org_service.py`
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin/overview.html`
- Modify: `app/templates/admin/organizations.html`
- Modify: `app/templates/base.html`
- Test: `tests/integration/test_university_admin.py`

**Interfaces:**
- Consumes: `ensure_actor_university`, `is_university_manager`
- Changes: `get_organization_tree(actor)` returns own-school counts/tree for `university_admin`
- Changes: `create_campus`, `create_station`, `assign_station_manager` accept platform admin or same-school university admin
- Changes: `list_all_stations`, `list_campuses`, `list_station_managers` filter to actor school for university admin
- Changes: `org_service.list_all_universities(actor)` returns only the actor school for university admin

- [ ] **Step 1: Write failing scope tests**

Assert school admin sees only school A counts, can create school A campus/station/assignment, cannot create university, and cannot create school B campus/station.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py -k "overview or organization" -v`

Expected: FAIL because admin routes still require `platform_admin`.

- [ ] **Step 3: Extend service authorization**

Replace platform-only checks in scoped organization functions with `ensure_actor_university`. Keep `create_university` and `update_university` platform-only. Apply the same authorization to `list_all_universities`; school admins never receive all universities.

- [ ] **Step 4: Extend routes and templates**

Allow `platform_admin` and `university_admin` on scoped routes. Hide university creation and platform-only controls from school admins. Add “本校管理” nav for `university_admin`.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py -k "overview or organization" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/services/org_service.py app/routes/admin.py app/templates/admin/overview.html app/templates/admin/organizations.html app/templates/base.html tests/integration/test_university_admin.py
git commit -m "feat: add scoped university organization management"
```

### Task 3: 本校账号与名单管理

**Files:**
- Modify: `app/services/auth_service.py`
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin/users.html`
- Modify: `app/templates/admin/student_imports.html`
- Test: `tests/integration/test_university_admin.py`

**Interfaces:**
- Changes: `list_all_users(actor)` filters `User.university_id == actor.university_id` for school admin and excludes platform admins
- Changes: `import_managed_accounts(...)` lets school admin create only `station_manager` in own school
- Changes: `import_students(...)` and `list_import_batches(...)` accept same-school university admin
- Produces: `set_user_status(actor, user_id: int, status: str)` for school admin to enable/disable own students and station managers
- Changes: `auth_service.list_universities(actor)` returns only the actor school for university admin

- [ ] **Step 1: Write failing tests**

Assert school admin sees only own users, creates only own station managers, imports only own roster, cannot disable university/platform admins, and cannot change IDs, roles or passwords of other schools.

Assign an own-school station manager to a station, disable that manager as school admin, and assert the assignment becomes `ended` with `ended_on` set.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py -k "users or roster" -v`

Expected: FAIL.

- [ ] **Step 3: Implement service scopes**

Use actor school as authoritative. Reject cross-school IDs. `set_user_status` accepts only `active|disabled`, rejects system admins and self-disable.

When disabling an own-school station manager, end all active station assignments in the same transaction and write audit. A disabled manager must not retain an active assignment.

- [ ] **Step 4: Update route forms and templates**

School admin forms omit university selector and role escalation. Platform admin behavior remains unchanged.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py -k "users or roster" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/services/auth_service.py app/routes/admin.py app/templates/admin/users.html app/templates/admin/student_imports.html tests/integration/test_university_admin.py
git commit -m "feat: add scoped university user and roster management"
```

### Task 4: 本校审核、争议与审计

**Files:**
- Modify: `app/services/item_service.py`
- Modify: `app/services/handover_service.py`
- Modify: `app/services/notification_service.py`
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin/moderation.html`
- Modify: `app/templates/admin/disputes.html`
- Modify: `app/templates/admin/audit.html`
- Test: `tests/integration/test_university_admin.py`

**Interfaces:**
- Changes: `list_recent_items(actor)` and forced `change_item_shelf_state(..., action="force_off_shelf")` accept same-school university admin
- Changes: `list_open_disputes(actor)` and `resolve_dispute(actor, dispute_id, ...)` accept same-school university admin
- Changes: `list_audit_logs(actor, limit=100)` filters `university_id` for university admin

- [ ] **Step 1: Write failing cross-school tests**

Create school A and B items/disputes/audits. Assert school A sees only A, can moderate/resolve A, and gets `PermissionDeniedError` for B.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py -k "moderation or dispute or audit" -v`

Expected: FAIL.

- [ ] **Step 3: Implement service scopes**

Apply platform-global or same-school authorization once per service. Keep existing state machine and lock order unchanged.

- [ ] **Step 4: Update routes/templates**

Allow both admin roles on scoped routes; school admin sees only school data. Do not expose record deletion.

Replace `test_university_admin_login_reserved` with a positive test asserting a school admin reaches the scoped dashboard and a cross-school object is rejected.

- [ ] **Step 5: Run G5-A regression**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_university_admin.py tests\integration\test_permissions.py tests\integration\test_admin_g3.py -v`

Expected: PASS.

- [ ] **Step 6: Commit and stop**

```powershell
git add app/services/item_service.py app/services/handover_service.py app/services/notification_service.py app/routes/admin.py app/templates/admin/moderation.html app/templates/admin/disputes.html app/templates/admin/audit.html tests/integration/test_university_admin.py
git commit -m "feat: add scoped university moderation and governance"
```

Stop: G5-A 门禁，提交测试证据，等待项目维护者 验收。

### Task 5: 注册验证数据模型与迁移

**Files:**
- Modify: `sql/schema.sql`
- Create: `sql/migrations/20261121_g5_registration_verification.sql`
- Create: `app/models/verification.py`
- Modify: `app/models/__init__.py`
- Modify: `tests/integration/test_health_and_errors.py`
- Create: `tests/integration/test_registration_verification.py`

**Interfaces:**
- Produces: `RegistrationVerificationRequest`
- Produces table `registration_verification_requests`; unmatched attempts use `status=ignored`, null registry/code fields, and only HMAC identifiers

- [ ] **Step 1: Write failing schema tests**

Assert the table exists with `university_id`, nullable `student_registry_record_id`, `student_no_hash`, `phone_hash`, nullable `code_hash`, nullable `salt`, `provider`, `status`, `request_ip_hash`, `failed_attempts`, `resend_after`, `expires_at`, and timestamps. Add checks that `ignored`/`aliyun_pnvs` rows may omit local code fields while `mock` active rows require them.

- [ ] **Step 2: Run failing tests on a fresh test database**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_health_and_errors.py tests\integration\test_registration_verification.py -v`

Expected: FAIL because the table/model is absent.

- [ ] **Step 3: Add model and additive migration**

Add `UNIQUE (id, university_id)` to `student_registry_records`, create a composite FK to it, create one-active-challenge partial unique index, and indexes for phone/IP rate checks. Migration must be idempotent only where PostgreSQL supports explicit guards; otherwise fail fast.

- [ ] **Step 4: Verify fresh schema and migration**

Run schema on an empty database and migration on a copy with existing school data.

Expected: both succeed; row counts outside the new table/unique constraint remain unchanged.

- [ ] **Step 5: Commit**

```powershell
git add sql/schema.sql sql/migrations/20261121_g5_registration_verification.sql app/models/verification.py app/models/__init__.py tests/integration/test_health_and_errors.py tests/integration/test_registration_verification.py
git commit -m "feat: add registration verification persistence"
```

### Task 6: 图形验证码与 SMS Provider

**Files:**
- Create: `app/core/captcha.py`
- Create: `app/core/sms.py`
- Modify: `app/config.py`
- Modify: `app/__init__.py`
- Modify: `requirements.txt`
- Modify: `.env.example`
- Create: `tests/unit/test_captcha.py`
- Create: `tests/unit/test_sms_provider.py`

**Interfaces:**
- Produces: `issue_captcha(session) -> bytes`
- Produces: `verify_captcha(session, answer: str) -> bool`
- Produces: `SmsSender.send_register_code(phone: str, out_id: str) -> SmsSendResult`
- Produces: `SmsSender.verify_register_code(phone: str, code: str, out_id: str) -> bool`
- Produces: `sms_sender_from_config(config: Config) -> SmsSender`

- [ ] **Step 1: Write failing tests**

Test captcha expiry/single use, Mock sender payload without phone logging and mock-code display only outside Production, PNVS send/check response mapping with a fake SDK client, template JSON `{"code":"##code##","min":"5"}`, and startup validation for missing Aliyun config.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_captcha.py tests\unit\test_sms_provider.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement captcha**

Use Pillow to render a PNG. Store only HMAC digest and expiry in Flask session. Clear digest after one verification attempt.

- [ ] **Step 4: Implement SMS providers**

`MockSmsSender` returns a synthetic ID and validates a local code. `AliyunPnvsSmsSender` uses `alibabacloud_dypnsapi20170525`, sends with `ReturnVerifyCode=false`, and calls `CheckSmsVerifyCode`; non-OK or non-PASS results map to domain errors without secrets.

- [ ] **Step 5: Extend config**

Add the PNVS environment variables and register the sender in `app.extensions["sms_sender"]`. In production, `aliyun_pnvs` with incomplete settings fails startup.

Read Vercel's `VERCEL_ENV`; reject `SMS_PROVIDER=mock` when it equals `production`. Mock responses may expose the synthetic code to the page only in non-Production mock mode.

Exact config names: `SMS_PROVIDER`, `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_ACCESS_KEY_SECRET`, `ALIYUN_PNVS_SIGN_NAME`, `ALIYUN_PNVS_TEMPLATE_CODE`, `ALIYUN_PNVS_REGION_ID`.

- [ ] **Step 6: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_captcha.py tests\unit\test_sms_provider.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/core/captcha.py app/core/sms.py app/config.py app/__init__.py requirements.txt .env.example tests/unit/test_captcha.py tests/unit/test_sms_provider.py
git commit -m "feat: add captcha and aliyun sms providers"
```

### Task 7: 注册验证服务

**Files:**
- Modify: `app/services/auth_service.py`
- Modify: `app/core/errors.py`
- Test: `tests/integration/test_registration_verification.py`

**Interfaces:**
- Produces: `request_registration_code(*, university_id, campus_id, student_no, phone, captcha_answer, request_ip) -> dict`
- Changes: `register_student(..., verification_request_id: int, sms_code: str) -> User`

- [ ] **Step 1: Write failing service tests**

Test roster match, generic response for mismatch, ignored-attempt IP rate tracking, cooldown, TTL, max attempts, duplicate request, successful registration, consumed replay rejection, provider failure and no account creation on failure.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_registration_verification.py -k "code or replay or provider" -v`

Expected: FAIL.

- [ ] **Step 3: Implement request flow**

Verify captcha, lock the registry row, record `ignored` for mismatch or expire/reject active challenge for a match, insert `pending`, commit, call PNVS SendSmsVerifyCode, update `sent|failed`. Hash IP with the existing secret-derived HMAC. If the post-send update cannot be proven, leave `pending` valid until expiry and do not resend during cooldown.

- [ ] **Step 4: Implement verified registration**

Lock challenge, accept `pending|sent`, validate TTL/attempts/phone/roster/campus, call PNVS CheckSmsVerifyCode, create the student and mark challenge `consumed` in one transaction. Remove `verified` from all states and UI copy.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_registration_verification.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/services/auth_service.py app/core/errors.py tests/integration/test_registration_verification.py
git commit -m "feat: add verified student registration flow"
```

### Task 8: 注册页面交互

**Files:**
- Modify: `app/routes/auth.py`
- Modify: `app/templates/auth/register.html`
- Create: `app/static/js/register.js`
- Modify: `app/static/css/register-auth.css`
- Modify: `tests/integration/test_register_and_login.py`
- Modify: `tests/integration/test_registration_verification.py`

- [ ] **Step 1: Write failing HTTP tests**

Assert captcha image endpoint has `Cache-Control: no-store`, SMS request requires CSRF and captcha, generic response text, resend countdown fields and successful full registration.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_register_and_login.py tests\integration\test_registration_verification.py -k "register or http" -v`

Expected: FAIL.

- [ ] **Step 3: Implement routes**

Add `GET /auth/register/captcha.png` and `POST /auth/register/sms-code`; extend registration POST with `verification_request_id` and `sms_code`.

- [ ] **Step 4: Implement UI**

Use progressive enhancement: all security checks remain server-side; JS only refreshes captcha, requests SMS, starts 60-second countdown and displays generic status. Provide text labels and keyboard-accessible controls.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_register_and_login.py tests\integration\test_registration_verification.py -v`

Expected: PASS.

- [ ] **Step 6: Commit and stop**

```powershell
git add app/routes/auth.py app/templates/auth/register.html app/static/js/register.js app/static/css/register-auth.css tests/integration/test_register_and_login.py tests/integration/test_registration_verification.py
git commit -m "feat: add registration captcha and sms UI"
```

Stop: G5-B 门禁，提交测试证据，等待项目维护者 验收。

### Task 9: 平台运维、攻击分类与日志

**Files:**
- Create: `app/models/security.py`
- Modify: `app/models/__init__.py`
- Create: `app/core/security_monitor.py`
- Create: `app/services/operations_service.py`
- Modify: `app/routes/admin.py`
- Modify: `app/blueprints` registration in `app/__init__.py`
- Create: `app/templates/admin/operations.html`
- Modify: `app/templates/admin/overview.html`
- Modify: `app/templates/base.html`
- Modify: `app/core/errors.py`
- Modify: `sql/schema.sql`
- Modify: `sql/migrations/20261121_g5_registration_verification.sql`
- Create: `tests/integration/test_operations_security.py`

**Interfaces:**
- Produces: `record_security_event(category: str, severity: str, subject_hash: str, detail: dict) -> None`
- Produces: `active_block_for_ip(ip_hash: str, route_scope: str) -> SecurityBlock | None`
- Produces: `list_security_events(actor, *, limit: int = 100) -> list[SecurityEvent]`
- Produces: `set_block_disposition(actor, block_id: int, action: str, reason: str) -> SecurityBlock`
- Produces: `operations_snapshot(actor) -> dict`

- [ ] **Step 1: Write failing tests**

Test classification for SMS IP threshold, captcha failure burst and blocked retry; school/admin access rejection; temporary block expiry; manual revoke and false-positive audit; error event redaction; 30-day retention filter.

- [ ] **Step 2: Run failing tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_operations_security.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement persistence and middleware**

Add `security_events`, `security_blocks`, `application_events`. Hook only `/auth/register/*` for automatic blocking. Persist errors in the existing error handlers with request ID and sanitized summary.

- [ ] **Step 4: Implement platform operations UI**

Add `/admin/operations` and nav only for platform admins. Render health, SMS/security counters, classified incidents, errors and filtered logs. No raw request bodies, IPs, phone numbers or secrets.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_operations_security.py tests\integration\test_health_and_errors.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/models/security.py app/models/__init__.py app/core/security_monitor.py app/services/operations_service.py app/routes/admin.py app/__init__.py app/templates/admin/operations.html app/templates/admin/overview.html app/templates/base.html app/core/errors.py sql/schema.sql sql/migrations/20261121_g5_registration_verification.sql tests/integration/test_operations_security.py
git commit -m "feat: add operations security monitoring"
```

### Task 10: Cloudflare Free 与应用层防火墙联动

**Files:**
- Modify: `app/core/security_monitor.py`
- Modify: `app/config.py`
- Modify `.env.example`
- Modify: `README.md`
- Create: `docs/6.3-development/cloudflare-free-firewall.md`
- Test: `tests/integration/test_operations_security.py`

**Interfaces:**
- Produces: `client_ip_hash(trusted_headers: Mapping[str, str]) -> str`
- Config: `TRUST_CLOUDFLARE_IP_HEADER=false|true`

- [ ] **Step 1: Write failing header tests**

Test Cloudflare header used only when explicitly enabled, direct clients cannot spoof the header, and all IP hashes use the same secret-derived HMAC.

- [ ] **Step 2: Implement trusted client IP**

When enabled by controlled deployment configuration, use `CF-Connecting-IP`; otherwise use the platform-supplied forwarded IP. Never trust a client-provided fallback header without a proxy boundary.

- [ ] **Step 3: Document Cloudflare setup**

Document custom domain, proxied DNS, Free Managed Ruleset, Bot Fight Mode and one rate limiting rule. State clearly that `vercel.app` cannot be protected by Cloudflare WAF.

- [ ] **Step 4: Preview verification**

Use a non-Production custom-domain Preview. Verify Cloudflare challenge/block events, application security event correlation, direct-origin bypass behavior and header spoof rejection.

- [ ] **Step 5: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_operations_security.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/core/security_monitor.py app/config.py .env.example README.md docs/6.3-development/cloudflare-free-firewall.md tests/integration/test_operations_security.py
git commit -m "docs: add cloudflare free waf rollout"
```

### Task 11: 全量验证、文档与发布候选

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/00-governance/engineering-standards.md`
- Modify: `docs/00-governance/collaboration-and-quality-gates.md`
- Modify: `docs/00-governance/glossary.md`
- Modify: `docs/00-governance/decision-log.md`
- Modify: `docs/6.1-requirements/需求规格说明书.md`
- Modify: `docs/6.2-design/03-architecture-design.md`
- Modify: `docs/6.2-design/04-global-conventions.md`
- Modify: `docs/6.2-design/05-ui-design-and-prototypes.md`
- Create: `docs/6.3-development/evidence/g5-release-evidence.md`
- Update generated course Word files

- [ ] **Step 1: Run full automated tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests -v`

Expected: all pass; no real SMS network request.

- [ ] **Step 2: Run lint**

Run: `.\.venv\Scripts\python.exe -m ruff check app tests`

Expected: `All checks passed!`.

- [ ] **Step 3: Run migration rehearsal**

Restore a production-schema copy into a separate PostgreSQL database, apply the migration, verify counts, run application smoke tests, then drop the copy.

- [ ] **Step 4: Configure Vercel Preview only**

Set SMS secrets in Preview, use `SMS_PROVIDER=aliyun_pnvs`, send one code to the maintainer-controlled test phone, verify `BizId`, expired/reused/cooldown paths, and confirm logs are redacted.

Store the smoke phone only in local `.env.local` as `SMS_SMOKE_TEST_PHONE`; never add it to `.env.example`, Git, evidence screenshots, command output or shell history.

- [ ] **Step 5: Verify attack firewall**

Send nine allowed registration-code attempts from one test IP with valid captcha; assert the ninth is blocked, the event is classified, the block expires after 15 minutes, and non-registration pages remain available. Verify a platform admin can revoke it with audit.

- [ ] **Step 6: Update documents and Word submissions**

Record actual test count, migration result, Aliyun smoke result and remaining limitations. Regenerate 6.1/6.2 Word files and run structure checks.

- [ ] **Step 7: 项目维护者 acceptance**

验收独立检查 own-school isolation, account escalation prevention, captcha replay, SMS provider failure, migration and secrets. 项目维护者 stops during review.

- [ ] **Step 8: Commit and stop**

```powershell
git add README.md .env.example docs
git commit -m "docs: complete g5 release evidence"
```

Stop: G5-R release candidate，等待用户批准切换 Production。

## G5 开发流程扩展

### 门禁

| 门禁 | 完成条件 | 停止指令 |
|---|---|---|
| G5-0 方案冻结 | 本文和设计提案获批；阿里云账号准备清单明确 | 项目维护者 不写代码 |
| G5-A 校级管理员 | 本校概览、组织、账号名单、审核争议审计通过 | 停止，项目维护者 验收 |
| G5-B 注册短信 | 图形码、模拟/真实 Provider、注册闭环与异常测试通过 | 停止，项目维护者 验收 |
| G5-C 运维治理 | 攻击分类、临时封禁、运行状况、错误日志与 Cloudflare 部署说明通过 | 停止，项目维护者 验收 |
| G5-R 发布候选 | 全量回归、迁移演练、Preview 阿里云 smoke、文档和 Word 同步 | 停止，用户批准 Production |

### 写入权

| 阶段 | 项目维护者 | 项目维护者 | 用户 |
|---|---|---|---|
| G5-0 | 设计、计划、范围检查 | 阅读并提交问题 | 批准范围和权限 |
| G5-A/B | 验收测试、审查、受控修复 | 业务代码、页面、测试、增量文档 | 配置阿里云、确认测试手机号 |
| G5-R | 独立验收、发布门禁 | 停止编辑 | 批准 Production |

### 分支与提交

- 分支：`feature/g5-university-admin-sms`
- 每个 Task 一个可回滚 commit。
- G5-A 和 G5-B 分别停止，不允许一口气实现后统一验收。
- 迁移脚本、应用代码和文档使用同一发布候选 commit。

### 数据库发布顺序

```text
备份 Neon
  → 在克隆库执行迁移与回归
  → Preview 部署新代码
  → 在 Production 执行添加式迁移
  → 部署 Production 应用
  → 验证本校权限和新注册
```

回滚应用不删除新表；恢复数据库只在迁移损坏或数据一致性失败时执行，并优先恢复备份。

### 验收证据

- 校级管理员跨校越权测试结果。
- 停用高校和停用公益管理员后有效授权自动结束的测试结果。
- 验证码重放、过期、次数和并发测试结果。
- Mock Provider 测试结果。
- 阿里云 Preview smoke 的 `BizId` 与脱敏日志。
- 迁移前后表/行数。
- 7 份 Word 结构检查。
- 公网健康、角色权限和一次完整学生注册记录。
