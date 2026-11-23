"""集成测试：身份选择、学校校区选择、注册、登录与角色（G1 基础鉴权）。"""

from __future__ import annotations

import re
from datetime import UTC

import pytest

from tests.fixtures.helpers import (
    create_campus,
    create_import_batch,
    create_platform_admin,
    create_registry_record,
    create_university,
)

pytestmark = pytest.mark.integration


def get_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "页面缺少 CSRF 令牌"
    return match.group(1)


def choose_student_identity(client) -> None:
    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "student"},
        follow_redirects=True,
    )


def choose_campus(client, university_id: int, campus_id: int) -> None:
    page = client.get("/auth/student-context").get_data(as_text=True)
    client.post(
        "/auth/student-context",
        data={
            "csrf_token": get_csrf_token(page),
            "university_id": str(university_id),
            "campus_id": str(campus_id),
        },
        follow_redirects=True,
    )


def submit_login(client, page_html: str, identifier: str, password: str, follow: bool = True):
    """携带 CSRF 令牌提交登录表单。"""
    return client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page_html),
            "identifier": identifier,
            "password": password,
        },
        follow_redirects=follow,
    )


def complete_registration(
    client,
    monkeypatch,
    *,
    student_no: str,
    phone: str,
    password: str = "abcd1234",
):
    monkeypatch.setattr(
        "app.services.auth_service.verify_captcha",
        lambda _session, answer: answer == "TEST",
    )
    page = client.get("/auth/register").get_data(as_text=True)
    sms = client.post(
        "/auth/register/sms-code",
        data={
            "csrf_token": get_csrf_token(page),
            "student_no": student_no,
            "phone": phone,
            "captcha": "TEST",
        },
        headers={"Accept": "application/json"},
    )
    assert sms.status_code == 202
    page = client.get("/auth/register").get_data(as_text=True)
    token = re.search(r'name="verification_request_id" value="([^"]+)"', page).group(1)
    return client.post(
        "/auth/register",
        data={
            "csrf_token": get_csrf_token(page),
            "verification_request_id": token,
            "student_no": student_no,
            "phone": phone,
            "password": password,
            "password_confirm": password,
            "sms_code": "123456",
        },
        follow_redirects=True,
    )


@pytest.fixture
def school(app):
    """构造一所单校区测试高校，并预置一条未注册的名单记录。"""
    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        admin, _ = create_platform_admin()
        batch = create_import_batch(uni, admin)
        record = create_registry_record(uni, campus, batch, phone="13880001234")
        record_id = record.id
        yield {"university_id": uni.id, "campus_id": campus.id, "record_id": record_id}


class TestIdentityFlow:
    def test_identity_page_lists_roles(self, client):
        html = client.get("/auth/identity").get_data(as_text=True)
        for label in ("在校学生", "公益管理员", "平台管理员", "校级管理员"):
            assert label in html

    def test_invalid_role_rejected(self, client):
        page = client.get("/auth/identity").get_data(as_text=True)
        resp = client.post(
            "/auth/identity", data={"csrf_token": get_csrf_token(page), "role": "hacker"}
        )
        assert resp.status_code == 400

    def test_index_redirects_anonymous_to_identity(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/auth/" in resp.headers["Location"]

    def test_login_page_has_accessible_enterprise_form(self, client):
        page = client.get("/auth/identity").get_data(as_text=True)
        resp = client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "platform_admin"},
            follow_redirects=True,
        )
        html = resp.get_data(as_text=True)
        assert 'class="login-shell"' in html
        assert 'id="account-label"' in html
        assert "登录账号" in html
        assert '<label for="password">密码</label>' in html
        assert 'id="password-toggle"' in html
        assert 'aria-controls="password"' in html
        assert 'name="remember_account"' in html
        assert 'class="identity-switcher"' in html
        assert 'id="identity-picker"' in html
        assert 'name="role" value="platform_admin"' in html
        assert "不需要再次确认" in html
        assert 'id="registration-guard-notice"' in html
        assert "data-theme-toggle" in html

    def test_login_security_verification_card_uses_local_fallback(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "LOGIN_VERIFICATION_ENABLED", True)
        page = client.get("/auth/identity").get_data(as_text=True)
        resp = client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "platform_admin"},
            follow_redirects=True,
        )
        html = resp.get_data(as_text=True)
        assert 'id="security-verification"' in html
        assert "security-verification--inline" in html
        assert "安全验证 · 防止自动化程序滥用" in html
        assert 'id="login-captcha-image"' in html
        assert 'name="verification_answer"' in html
        assert "challenges.cloudflare.com" not in html

    def test_login_requires_security_verification(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "LOGIN_VERIFICATION_ENABLED", True)
        page = client.get("/auth/login").get_data(as_text=True)
        resp = client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "role": "platform_admin",
                "identifier": "admin",
                "password": "admin12345",
                "verification_answer": "WRONG",
            },
        )
        assert resp.status_code == 400
        assert "安全验证未通过" in resp.get_data(as_text=True)

    def test_turnstile_replaces_local_captcha_when_configured(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "LOGIN_VERIFICATION_ENABLED", True)
        app_config = app.config["APP_CONFIG"]
        monkeypatch.setattr(app_config, "turnstile_site_key", "site-key-for-test")
        monkeypatch.setattr(app_config, "turnstile_secret_key", "secret-key-for-test")
        monkeypatch.setattr(app_config, "turnstile_configured", True)

        page = client.get("/auth/login").get_data(as_text=True)
        assert 'class="cf-turnstile"' in page
        assert 'data-sitekey="site-key-for-test"' in page
        assert 'data-size="flexible"' in page
        assert "security-verification--inline" in page
        assert 'id="login-captcha-image"' not in page
        assert 'src="https://challenges.cloudflare.com/turnstile/v0/api.js"' in page
        assert 'id="login-captcha-image"' not in page

    def test_login_page_prompts_when_identity_is_not_selected(self, client):
        resp = client.get("/auth/login?next=/me/profile")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "未选择身份" in html
        assert "请先在右上角选择登录身份" in html
        assert 'name="next" value="/me/profile"' in html
        assert 'id="login-form"' in html

    def test_live_identity_selection_unblocks_student_context_and_register(
        self, client, school
    ):
        page = client.get("/auth/login").get_data(as_text=True)
        resp = client.post(
            "/auth/select-role",
            data={"csrf_token": get_csrf_token(page), "role": "student"},
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True, "role": "student"}

        context = client.get("/auth/student-context")
        assert context.status_code == 200
        choose_campus(client, school["university_id"], school["campus_id"])
        register = client.get("/auth/register")
        assert register.status_code == 200
        assert "学生注册" in register.get_data(as_text=True)


class TestRegister:
    def test_register_success_and_login(self, client, app, school, monkeypatch):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])

        page = client.get("/auth/register").get_data(as_text=True)
        assert "测试大学" in page  # 学校信息由上下文带入
        assert 'class="login-shell register-shell"' in page
        assert 'class="identity-visual"' in page
        assert 'id="student_no"' in page
        assert 'id="password_confirm"' in page

        resp = complete_registration(
            client,
            monkeypatch,
            student_no="2024001",
            phone="13880001234",
        )
        html = resp.get_data(as_text=True)
        assert "注册成功" in html

        # 名单记录被标记为已注册
        with app.app_context():
            from app import db
            from app.models.university import StudentRegistryRecord

            record = db.session.get(StudentRegistryRecord, school["record_id"])
            assert record.registered_user_id is not None

        # 用学号登录
        page = client.get("/auth/login").get_data(as_text=True)
        resp = submit_login(client, page, "2024001", "abcd1234")
        html = resp.get_data(as_text=True)
        assert "张测试" in html  # 昵称来自名单姓名
        assert "学生" in html  # 角色标签

    def test_register_student_no_not_in_roster(self, client, school, monkeypatch):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        monkeypatch.setattr(
            "app.services.auth_service.verify_captcha",
            lambda _session, answer: answer == "TEST",
        )
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "9999999",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.get_json()["message"] == "如果名单信息匹配，验证码将发送到预留手机号。"
        assert "学号不在本校名单中" not in resp.get_json()["message"]

    def test_register_phone_mismatch(self, client, school, monkeypatch):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        monkeypatch.setattr(
            "app.services.auth_service.verify_captcha",
            lambda _session, answer: answer == "TEST",
        )
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13900000000",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.get_json()["message"] == "如果名单信息匹配，验证码将发送到预留手机号。"
        assert "手机号与名单记录不符" not in resp.get_json()["message"]

    def test_register_duplicate_rejected(self, client, app, school, monkeypatch):
        # 名单记录已注册
        with app.app_context():
            from app import db
            from app.models.university import StudentRegistryRecord

            record = db.session.get(StudentRegistryRecord, school["record_id"])
            from datetime import datetime

            from app.models.user import User
            from app.services.auth_service import hash_password
            from tests.fixtures.helpers import db_add

            user = User(
                university_id=record.university_id,
                campus_id=record.campus_id,
                student_no=record.student_no,
                phone_hash=record.phone_hash,
                password_hash=hash_password("already1"),
                nickname="已注册学生",
                role="student",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_add(user)
            record.registered_user_id = user.id
            db.session.commit()
            assert record.registered_user_id == user.id

        with app.app_context():
            from app.models.university import StudentRegistryRecord

            persisted = db.session.get(StudentRegistryRecord, school["record_id"])
            assert persisted.registered_user_id is not None

        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        monkeypatch.setattr(
            "app.services.auth_service.verify_captcha",
            lambda _session, answer: answer == "TEST",
        )
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.get_json()["message"] == "如果名单信息匹配，验证码将发送到预留手机号。"
        assert "mock_code" not in resp.get_json()
        with app.app_context():
            from app.models.verification import RegistrationVerificationRequest

            assert db.session.query(RegistrationVerificationRequest).one().status == "ignored"

    def test_register_password_format_rejected(self, client, school, monkeypatch):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        monkeypatch.setattr(
            "app.services.auth_service.verify_captcha",
            lambda _session, answer: answer == "TEST",
        )
        page = client.get("/auth/register").get_data(as_text=True)
        sms = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        assert sms.status_code == 202
        page = client.get("/auth/register").get_data(as_text=True)
        token = re.search(r'name="verification_request_id" value="([^"]+)"', page).group(1)
        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "verification_request_id": token,
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "short",
                "password_confirm": "short",
                "sms_code": "123456",
            },
        )
        html = resp.get_data(as_text=True)
        assert "密码长度至少 8 位" in html


class TestRegisterVerificationHttp:
    def _start_registration(self, client, school, monkeypatch):
        monkeypatch.setattr(
            "app.services.auth_service.verify_captcha",
            lambda _session, answer: answer == "TEST",
        )
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        return page, get_csrf_token(page)

    def test_captcha_image_has_no_store(self, client, school, monkeypatch):
        self._start_registration(client, school, monkeypatch)

        response = client.get("/auth/register/captcha.png")

        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.data.startswith(b"\x89PNG\r\n\x1a\n")

    def test_sms_code_endpoint_is_generic_and_returns_mock_code(
        self, client, school, monkeypatch
    ):
        _page, token = self._start_registration(client, school, monkeypatch)

        response = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": token,
                "student_no": "2024001",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 202
        body = response.get_json()
        assert body["message"] == "如果名单信息匹配，验证码将发送到预留手机号。"
        assert body["mock_code"] == "123456"
        assert body["resend_after"] > 0
        assert "13880001234" not in response.get_data(as_text=True)

    def test_sms_code_mismatch_does_not_reveal_roster(self, client, school, monkeypatch):
        _page, token = self._start_registration(client, school, monkeypatch)

        response = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": token,
                "student_no": "9999999",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 202
        assert response.get_json()["message"] == "如果名单信息匹配，验证码将发送到预留手机号。"
        assert "名单" not in response.get_data(as_text=True)
        assert "学号" not in response.get_data(as_text=True)

    def test_full_verified_registration(self, client, school, monkeypatch):
        _page, token = self._start_registration(client, school, monkeypatch)
        sms = client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": token,
                "student_no": "2024001",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        assert sms.status_code == 202

        page = client.get("/auth/register").get_data(as_text=True)
        assert 'id="mock-sms-code"' in page
        assert "123456" in page
        assert 'name="verification_request_id"' in page
        assert 'id="sms_code"' in page

        response = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "verification_request_id": re.search(
                    r'name="verification_request_id" value="([^"]+)"', page
                ).group(1),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
                "sms_code": "123456",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "注册成功" in response.get_data(as_text=True)

    def test_wrong_sms_code_creates_no_account(self, client, school, monkeypatch):
        _page, token = self._start_registration(client, school, monkeypatch)
        client.post(
            "/auth/register/sms-code",
            data={
                "csrf_token": token,
                "student_no": "2024001",
                "phone": "13880001234",
                "captcha": "TEST",
            },
            headers={"Accept": "application/json"},
        )
        page = client.get("/auth/register").get_data(as_text=True)
        response = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "verification_request_id": re.search(
                    r'name="verification_request_id" value="([^"]+)"', page
                ).group(1),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
                "sms_code": "000000",
            },
        )

        assert response.status_code == 400
        assert "短信验证码不正确" in response.get_data(as_text=True)


class TestLogin:
    def test_login_by_phone(self, client, app, school, monkeypatch):
        # 先注册
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        complete_registration(
            client,
            monkeypatch,
            student_no="2024001",
            phone="13880001234",
        )
        # 手机号登录
        page = client.get("/auth/login").get_data(as_text=True)
        resp = submit_login(client, page, "13880001234", "abcd1234")
        assert "张测试" in resp.get_data(as_text=True)

    def test_login_wrong_password(self, client, app, school):
        with app.app_context():
            from datetime import datetime

            from app.models.user import User
            from app.services.auth_service import hash_password
            from tests.fixtures.helpers import db_add

            user = User(
                university_id=school["university_id"],
                campus_id=school["campus_id"],
                student_no="2024002",
                phone_hash="b" * 64,
                password_hash=hash_password("goodpass1"),
                nickname="另一名学生",
                role="student",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_add(user)

        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/login").get_data(as_text=True)
        resp = submit_login(client, page, "2024002", "wrongpass", follow=False)
        html = resp.get_data(as_text=True)
        assert "账号或密码不正确" in html
        # 未建立会话：访问首页仍跳登录
        assert client.get("/", follow_redirects=False).status_code == 302

    def test_login_cross_university_rejected(self, client, app, school):
        """FR-A08：学生账号必须属于所选学校；外校账号在所选学校下不可登录。"""
        with app.app_context():
            other_uni = create_university(code="520002", name="外校大学")
            other_campus = create_campus(other_uni, code="MAIN2")
            from datetime import datetime

            from app.core.auth import phone_hash
            from app.models.user import User
            from app.services.auth_service import hash_password
            from tests.fixtures.helpers import db_add

            stranger = User(
                university_id=other_uni.id,
                campus_id=other_campus.id,
                student_no="2024003",
                phone_hash=phone_hash("13711112222"),
                password_hash=hash_password("stranger1"),
                nickname="外校学生",
                role="student",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_add(stranger)

        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/login").get_data(as_text=True)
        resp = submit_login(client, page, "2024003", "stranger1", follow=False)
        assert "账号或密码不正确" in resp.get_data(as_text=True)

    def test_student_must_choose_campus_first(self, client):
        choose_student_identity(client)
        # 未选学校时登录页原位提示先完成学校校区选择（BR-044、FR-A08）
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "先选择学校与校区" in html
        assert "/auth/student-context" in html


class TestAdminLogin:
    def test_platform_admin_login_and_role_tag(self, client, app):
        with app.app_context():
            create_platform_admin(login_name="admin01", password="admin12345")

        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "platform_admin"},
            follow_redirects=True,
        )
        page = client.get("/auth/login").get_data(as_text=True)
        assert "平台管理员登录" in page
        assert "不提供注册入口" in page

        resp = submit_login(client, page, "admin01", "admin12345")
        html = resp.get_data(as_text=True)
        assert "平台管理员" in html  # 标签
        assert "平台管理员" in html  # 昵称

    def test_logout(self, client, app):
        with app.app_context():
            create_platform_admin(login_name="admin02", password="admin12345")
        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "platform_admin"},
            follow_redirects=True,
        )
        page = client.get("/auth/login").get_data(as_text=True)
        submit_login(client, page, "admin02", "admin12345")
        page = client.get("/").get_data(as_text=True)
        resp = client.post(
            "/auth/logout",
            data={"csrf_token": get_csrf_token(page)},
            follow_redirects=True,
        )
        assert "选择登录身份" in resp.get_data(as_text=True)
        assert client.get("/", follow_redirects=False).status_code == 302


class TestUniversityAdminLogin:
    def test_university_admin_login_reaches_scoped_dashboard(self, client, app, school):
        """校级管理员可登录并进入本校管理范围（D-054）。"""
        with app.app_context():
            from datetime import datetime

            from app.models.user import User
            from app.services.auth_service import hash_password
            from tests.fixtures.helpers import db_add

            user = User(
                university_id=school["university_id"],
                login_name="uniadmin01",
                password_hash=hash_password("uniadmin1"),
                nickname="校级管理员",
                role="university_admin",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_add(user)

        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "university_admin"},
            follow_redirects=True,
        )
        page = client.get("/auth/login").get_data(as_text=True)
        assert "进入本校管理范围" in page
        assert "暂未开放" not in page
        resp = submit_login(client, page, "uniadmin01", "uniadmin1")
        assert "校级管理员" in resp.get_data(as_text=True)
