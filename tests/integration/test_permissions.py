"""集成测试：权限守卫、角色访问控制与会话安全（G1 基础鉴权核心证据）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.fixtures.helpers import create_platform_admin, db_add
from tests.integration.test_register_and_login import (
    choose_campus,
    choose_student_identity,
    get_csrf_token,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def school(app):
    """测试高校：校区 + 名单记录（供学生注册）。"""
    from tests.fixtures.helpers import (
        create_campus,
        create_import_batch,
        create_platform_admin,
        create_registry_record,
        create_university,
    )

    with app.app_context():
        uni = create_university()
        campus = create_campus(uni)
        admin, _ = create_platform_admin()
        batch = create_import_batch(uni, admin)
        create_registry_record(uni, campus, batch, student_no="2024010", phone="13650001111")
        yield {"university_id": uni.id, "campus_id": campus.id}


def login_student(client, school, student_no="2024010", password="stu-pass1"):
    """注册并登录一名学生，返回登录后的会话。"""
    choose_student_identity(client)
    choose_campus(client, school["university_id"], school["campus_id"])
    page = client.get("/auth/register").get_data(as_text=True)
    client.post(
        "/auth/register",
        data={
            "csrf_token": get_csrf_token(page),
            "student_no": student_no,
            "phone": "13650001111",
            "password": password,
            "password_confirm": password,
        },
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    return client.post(
        "/auth/login",
        data={"csrf_token": get_csrf_token(page), "identifier": student_no, "password": password},
        follow_redirects=True,
    )


class TestLoginRequired:
    def test_anonymous_profile_redirects_to_login_with_next(self, client):
        resp = client.get("/me/profile", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/auth/login" in location
        assert "next=" in location

    def test_anonymous_index_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]

    def test_student_profile_shows_role_tag(self, client, app, school):
        login_student(client, school)
        resp = client.get("/me/profile")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "个人资料" in html
        assert "2024010" in html
        assert "role-student" in html

    def test_student_can_render_empty_item_discovery(self, client, app, school):
        login_student(client, school)
        resp = client.get("/items")
        assert resp.status_code == 200
        assert "暂无符合条件的物品" in resp.get_data(as_text=True)


class TestRolesRequired:
    def test_student_forbidden_on_admin(self, client, app, school):
        """学生访问管理台必须返回 403（权限矩阵）。"""
        login_student(client, school)
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 403
        html = client.get("/admin").get_data(as_text=True)
        assert "没有访问权限" in html
        assert "下一步" in html

    def test_student_forbidden_on_station_workbench(self, client, app, school):
        """站点工作台仅对公益管理员开放，学生不得进入空壳页面。"""
        login_student(client, school)
        resp = client.get("/station", follow_redirects=False)
        assert resp.status_code == 403

    def test_platform_admin_accesses_overview(self, client, app, school):
        with app.app_context():
            create_platform_admin(login_name="adminx", password="admin12345")
        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "platform_admin"},
            follow_redirects=True,
        )
        page = client.get("/auth/login").get_data(as_text=True)
        client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": "adminx",
                "password": "admin12345",
            },
            follow_redirects=True,
        )
        resp = client.get("/admin")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "平台概览" in html
        assert "高校" in html
        assert '<span class="stat-num">0</span><span class="stat-label">物品</span>' in html

    def test_disabled_account_treated_as_not_logged_in(self, client, app, school):
        """账号停用后，会话失效并跳转登录（工程标准第 5 节）。"""
        login_student(client, school)
        with app.app_context():
            from sqlalchemy import select

            from app import db
            from app.models.user import User

            user = db.session.scalar(select(User).where(User.student_no == "2024010"))
            user.status = "disabled"
            db.session.commit()
        resp = client.get("/me/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


class TestStationManagerLogin:
    def test_station_manager_login_and_role_tag(self, client, app, school):
        """公益管理员（回收）登录：账号由平台管理员导入，无注册入口。"""
        with app.app_context():
            from app.models.user import User
            from app.services.auth_service import hash_password

            user = User(
                university_id=school["university_id"],
                login_name="station01",
                password_hash=hash_password("station1x"),
                nickname="站点管理员",
                role="station_manager",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db_add(user)

        page = client.get("/auth/identity").get_data(as_text=True)
        client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "station_manager"},
            follow_redirects=True,
        )
        page = client.get("/auth/login").get_data(as_text=True)
        assert "公益管理员（回收）登录" in page
        assert "不提供注册入口" in page

        resp = client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": "station01",
                "password": "station1x",
            },
            follow_redirects=True,
        )
        html = resp.get_data(as_text=True)
        assert "站点管理员" in html
        assert "role-station_manager" in html


class TestStudentContextEnforced:
    def test_student_without_campus_redirected(self, client):
        """学生未选校区时不能进入登录页（BR-044、FR-A08）。"""
        choose_student_identity(client)
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/student-context" in resp.headers["Location"]

    def test_student_without_campus_cannot_login(self, client):
        """未选校区时直接 POST 登录被重定向回学校校区选择。"""
        choose_student_identity(client)
        page = client.get("/auth/student-context").get_data(as_text=True)
        resp = client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": "2024099",
                "password": "whatever1",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/student-context" in resp.headers["Location"]


class TestHttpExceptionPages:
    def test_405_returns_chinese_page(self, client):
        """POST /health（携带有效 CSRF）得到中文 405 页，含原因与下一步。"""
        page = client.get("/auth/identity").get_data(as_text=True)
        resp = client.post("/health", data={"csrf_token": get_csrf_token(page)})
        assert resp.status_code == 405
        html = resp.get_data(as_text=True)
        assert "请求方式不正确" in html
        assert "下一步" in html


class TestOrgServicePermission:
    """service 层权限复验：绕过路由直接调用也必须校验角色（工程标准第 5 节）。"""

    def test_service_rejects_anonymous_actor(self, app):
        with app.app_context():
            from app.core.errors import PermissionDeniedError
            from app.services.org_service import get_organization_tree

            with pytest.raises(PermissionDeniedError):
                get_organization_tree(None)

    def test_service_rejects_non_admin_actor(self, app, school):
        with app.app_context():
            from app.core.errors import PermissionDeniedError
            from app.core.permissions import CurrentUser
            from app.services.org_service import get_organization_tree

            student_actor = CurrentUser(
                id=1,
                role="student",
                role_label="学生",
                nickname="学生",
                university_id=school["university_id"],
                campus_id=school["campus_id"],
                login_name=None,
                student_no="2024010",
            )
            with pytest.raises(PermissionDeniedError):
                get_organization_tree(student_actor)

    def test_service_allows_platform_admin(self, app, school):
        with app.app_context():
            from app.core.permissions import CurrentUser
            from app.services.org_service import get_organization_tree

            admin_actor = CurrentUser(
                id=99,
                role="platform_admin",
                role_label="平台管理员",
                nickname="管理员",
                university_id=None,
                campus_id=None,
                login_name="adminx",
                student_no=None,
            )
            data = get_organization_tree(admin_actor)
            assert data["counts"]["universities"] == 1


class TestNextTargetChain:
    """next 闭环：未登录访问 -> 登录后回到原目标页（SRS 异常需求）。"""

    def test_full_chain_returns_to_original_target(self, client, app, school):
        # 1) 匿名访问资料页 -> 跳登录并保留目标
        resp = client.get("/me/profile", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/auth/login" in location and "next=" in location

        # 2) 登录页（未选身份）-> 身份选择页，next 不丢失
        resp = client.get(location, follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/identity" in resp.headers["Location"]
        assert "next=" in resp.headers["Location"]

        # 3) 选择学生身份 -> 学校校区选择，next 仍保留
        page = client.get("/auth/identity").get_data(as_text=True)
        resp = client.post(
            "/auth/identity",
            data={"csrf_token": get_csrf_token(page), "role": "student", "next": "/me/profile"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/student-context" in resp.headers["Location"]
        assert "next=" in resp.headers["Location"]

        # 4) 选择学校校区 -> 登录页，next 仍保留
        page = client.get(resp.headers["Location"]).get_data(as_text=True)
        resp = client.post(
            "/auth/student-context",
            data={
                "csrf_token": get_csrf_token(page),
                "university_id": str(school["university_id"]),
                "campus_id": str(school["campus_id"]),
                "next": "/me/profile",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]
        assert "next=" in resp.headers["Location"]

        # 5) 先完成注册（名单记录由 school 夹具预置），注册后仍携带 next
        page = client.get("/auth/register").get_data(as_text=True)
        client.post(
            "/auth/register",
            data={
                "csrf_token": get_csrf_token(page),
                "student_no": "2024010",
                "phone": "13650001111",
                "password": "stu-pass1",
                "password_confirm": "stu-pass1",
            },
            follow_redirects=False,
        )

        # 6) 登录成功 -> 最终落点必须是原目标页 /me/profile
        page = client.get(resp.headers["Location"]).get_data(as_text=True)
        resp = client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": "2024010",
                "password": "stu-pass1",
                "next": "/me/profile",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/me/profile" in resp.headers["Location"]
        final = client.get("/me/profile")
        assert final.status_code == 200
        assert "个人资料" in final.get_data(as_text=True)

    def test_open_redirect_rejected(self, client, app, school):
        """协议相对地址 //evil.com 作为 next 必须被丢弃，登录后回首页。"""
        login_student(client, school)
        page = client.get("/").get_data(as_text=True)
        resp = client.post(
            "/auth/login",
            data={
                "csrf_token": get_csrf_token(page),
                "identifier": "2024010",
                "password": "stu-pass1",
                "next": "//evil.com",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "evil.com" not in resp.headers["Location"]
