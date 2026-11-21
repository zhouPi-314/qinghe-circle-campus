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
        for label in ("在校学生", "公益管理员（回收）", "平台管理员", "校级管理员（预留）"):
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
        assert '<label for="identifier">登录账号</label>' in html
        assert '<label for="password">密码</label>' in html
        assert 'id="password-toggle"' in html
        assert 'aria-controls="password"' in html
        assert 'name="remember_account"' in html


class TestRegister:
    def test_register_success_and_login(self, client, app, school):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])

        page = client.get("/auth/register").get_data(as_text=True)
        assert "测试大学" in page  # 学校信息由上下文带入

        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
            },
            follow_redirects=True,
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

    def test_register_student_no_not_in_roster(self, client, school):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "9999999",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
            },
        )
        html = resp.get_data(as_text=True)
        assert "学号不在本校名单中" in html

    def test_register_phone_mismatch(self, client, school):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13900000000",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
            },
        )
        html = resp.get_data(as_text=True)
        assert "手机号与名单记录不符" in html

    def test_register_duplicate_rejected(self, client, app, school):
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

        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
            },
        )
        html = resp.get_data(as_text=True)
        assert "已注册过账号" in html
        assert "登录" in html  # 引导登录

    def test_register_password_format_rejected(self, client, school):
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        resp = client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "short",
                "password_confirm": "short",
            },
        )
        html = resp.get_data(as_text=True)
        assert "密码长度至少 8 位" in html


class TestLogin:
    def test_login_by_phone(self, client, app, school):
        # 先注册
        choose_student_identity(client)
        choose_campus(client, school["university_id"], school["campus_id"])
        page = client.get("/auth/register").get_data(as_text=True)
        client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024001",
                "phone": "13880001234",
                "password": "abcd1234",
                "password_confirm": "abcd1234",
            },
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
        # 未选学校时访问登录页必须被拦截并回到学校校区选择（BR-044、FR-A08）
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/student-context" in resp.headers["Location"]


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


class TestReservedUniversityAdmin:
    def test_university_admin_login_reserved(self, client, app, school):
        """校级管理员为预留身份：可登录但无管理功能（SRS 第 3 节）。"""
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
        resp = submit_login(client, page, "uniadmin01", "uniadmin1")
        assert "校级管理员（预留）" in resp.get_data(as_text=True)
