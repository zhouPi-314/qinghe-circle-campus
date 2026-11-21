"""校级管理员权限快照与数据库范围校验。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import db
from app.core.errors import PermissionDeniedError
from app.core.permissions import CurrentUser, ensure_actor_university, to_current_user
from app.models.governance import AuditLog
from app.models.university import StationManagerAssignment, University
from app.models.user import User
from app.services import auth_service, org_service
from app.services.auth_service import hash_password
from tests.fixtures.helpers import (
    assign_manager,
    create_campus,
    create_platform_admin,
    create_station,
    create_station_manager_user,
    create_student_user,
    create_university,
    db_add,
)
from tests.integration.test_register_and_login import get_csrf_token

pytestmark = pytest.mark.integration


def _create_university_admin(university: University, login_name: str) -> User:
    now = datetime.now(UTC)
    return db_add(
        User(
            university_id=university.id,
            login_name=login_name,
            password_hash=hash_password("manager1"),
            nickname="校级管理员",
            role="university_admin",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture
def schools(app):
    with app.app_context():
        school_a = create_university(code="510101", name="甲大学")
        school_b = create_university(code="510102", name="乙大学")
        campus_a = create_campus(school_a, code="A-MAIN", name="甲主校区")
        campus_b = create_campus(school_b, code="B-MAIN", name="乙主校区")
        admin = _create_university_admin(school_a, "school-a-admin")
        admin_b = _create_university_admin(school_b, "school-b-admin")
        platform_admin, _ = create_platform_admin(login_name="platform-a")
        manager_a = create_station_manager_user(
            school_a, login_name="a-station", nickname="甲公益管理员"
        )
        manager_b = create_station_manager_user(
            school_b, login_name="b-station", nickname="乙公益管理员"
        )
        station_a = create_station(school_a, campus_a, name="甲站点")
        station_b = create_station(school_b, campus_b, name="乙站点")
        assignment_a = assign_manager(station_a, manager_a)
        student_a = create_student_user(
            school_a, campus_a, student_no="2025011", phone="13900005011"
        )
        student_b = create_student_user(
            school_b, campus_b, student_no="2025012", phone="13900005012"
        )
        yield {
            "a_id": school_a.id,
            "b_id": school_b.id,
            "a_campus_id": campus_a.id,
            "b_campus_id": campus_b.id,
            "a_manager_id": manager_a.id,
            "b_manager_id": manager_b.id,
            "a_station_id": station_a.id,
            "b_station_id": station_b.id,
            "a_assignment_id": assignment_a.id,
            "a_student_id": student_a.id,
            "b_student_id": student_b.id,
            "b_admin_id": admin_b.id,
            "platform_admin_id": platform_admin.id,
            "actor": to_current_user(admin),
            "platform_actor": to_current_user(platform_admin),
        }


def test_current_user_exposes_university_admin_role(schools):
    actor = schools["actor"]
    assert actor.is_university_admin
    assert not actor.is_platform_admin


def test_school_admin_can_use_own_active_university(schools):
    actor = schools["actor"]
    assert ensure_actor_university(actor, schools["a_id"]) == schools["a_id"]


def test_school_admin_cannot_use_other_university(schools):
    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(schools["actor"], schools["b_id"])


def test_inactive_university_is_rejected(app, schools):
    with app.app_context():
        university = db.session.get(University, schools["a_id"])
        university.status = "inactive"
        db.session.commit()
        assert university.status == "inactive"

    db.session.expire_all()
    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(schools["actor"], schools["a_id"])


def test_missing_university_is_rejected(schools):
    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(schools["actor"], 999999)


def test_platform_admin_can_use_school_scope(schools):
    actor = CurrentUser(
        id=99,
        role="platform_admin",
        role_label="平台管理员",
        nickname="平台管理员",
        university_id=None,
        campus_id=None,
        login_name="platform",
        student_no=None,
    )

    assert ensure_actor_university(actor, schools["b_id"]) == schools["b_id"]


def _platform_actor() -> CurrentUser:
    return CurrentUser(
        id=99,
        role="platform_admin",
        role_label="平台管理员",
        nickname="平台管理员",
        university_id=None,
        campus_id=None,
        login_name="platform",
        student_no=None,
    )


def test_school_admin_overview_is_scoped_to_own_school(schools):
    data = org_service.get_organization_tree(schools["actor"])

    assert data["counts"]["universities"] == 1
    assert data["counts"]["campuses"] == 1
    assert data["counts"]["stations"] == 1
    assert [row["name"] for row in data["universities"]] == ["甲大学"]


def test_platform_admin_overview_remains_global(schools):
    data = org_service.get_organization_tree(_platform_actor())

    assert data["counts"]["universities"] == 2
    assert {row["name"] for row in data["universities"]} == {"甲大学", "乙大学"}


def test_school_admin_organization_lists_are_scoped(schools):
    actor = schools["actor"]

    assert [row.id for row in org_service.list_all_universities(actor)] == [schools["a_id"]]
    assert [row.id for row in org_service.list_campuses(actor)] == [schools["a_campus_id"]]
    assert [row.id for row in org_service.list_all_stations(actor)] == [schools["a_station_id"]]
    assert [row.id for row in org_service.list_station_managers(actor)] == [
        schools["a_manager_id"]
    ]


def test_platform_admin_organization_lists_are_global(schools):
    actor = _platform_actor()

    assert {row.id for row in org_service.list_all_universities(actor)} == {
        schools["a_id"],
        schools["b_id"],
    }
    assert {row.id for row in org_service.list_campuses(actor)} == {
        schools["a_campus_id"],
        schools["b_campus_id"],
    }
    assert {row.id for row in org_service.list_all_stations(actor)} == {
        schools["a_station_id"],
        schools["b_station_id"],
    }


def test_school_admin_can_create_own_campus_and_station(schools):
    actor = schools["actor"]
    campus = org_service.create_campus(
        actor,
        university_id=schools["a_id"],
        code="A-EAST",
        name="甲东校区",
    )
    station = org_service.create_station(
        actor,
        university_id=schools["a_id"],
        campus_id=campus.id,
        name="甲东站点",
        station_type="mixed",
        address="甲东门",
    )
    assignment = org_service.assign_station_manager(
        actor,
        station_id=station.id,
        user_id=schools["a_manager_id"],
        started_on=datetime.now(UTC).date(),
    )

    assert campus.university_id == schools["a_id"]
    assert station.university_id == schools["a_id"]
    assert assignment.user_id == schools["a_manager_id"]


def test_school_admin_cannot_create_other_school_organization(schools):
    actor = schools["actor"]

    with pytest.raises(PermissionDeniedError):
        org_service.create_campus(
            actor,
            university_id=schools["b_id"],
            code="B-ILLEGAL",
            name="越权校区",
        )
    with pytest.raises(PermissionDeniedError):
        org_service.create_station(
            actor,
            university_id=schools["b_id"],
            campus_id=schools["b_campus_id"],
            name="越权站点",
            station_type="mixed",
            address="乙校门",
        )
    with pytest.raises(PermissionDeniedError):
        org_service.assign_station_manager(
            actor,
            station_id=schools["b_station_id"],
            user_id=schools["b_manager_id"],
            started_on=datetime.now(UTC).date(),
        )


def test_inactive_school_admin_organization_is_rejected(app, schools):
    with app.app_context():
        university = db.session.get(University, schools["a_id"])
        university.status = "inactive"
        db.session.commit()

    db.session.expire_all()
    with pytest.raises(PermissionDeniedError):
        org_service.get_organization_tree(schools["actor"])


def test_school_admin_can_render_scoped_admin_pages(client, schools):
    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "university_admin"},
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page),
            "identifier": "school-a-admin",
            "password": "manager1",
        },
        follow_redirects=True,
    )

    overview = client.get("/admin")
    assert overview.status_code == 200
    assert "本校管理" in overview.get_data(as_text=True)
    assert "甲大学" in overview.get_data(as_text=True)
    assert "乙大学" not in overview.get_data(as_text=True)

    organizations = client.get("/admin/organizations")
    assert organizations.status_code == 200
    html = organizations.get_data(as_text=True)
    assert "创建校区" in html
    assert "创建站点" in html
    assert "新增高校" not in html


def test_school_admin_user_and_university_lists_are_scoped(schools):
    actor = schools["actor"]

    users = auth_service.list_all_users(actor)
    assert {user.id for user in users} == {
        actor.id,
        schools["a_manager_id"],
        schools["a_student_id"],
    }
    assert all(user.role != "platform_admin" for user in users)
    assert [university.id for university in auth_service.list_universities(actor)] == [
        schools["a_id"]
    ]


def test_school_admin_can_create_only_own_station_manager(schools):
    created = auth_service.import_managed_accounts(
        schools["actor"],
        university_id=schools["a_id"],
        login_name="a-station-new",
        role="station_manager",
        password="station2x",
        nickname="甲新管理员",
    )

    assert created.university_id == schools["a_id"]
    assert created.role == "station_manager"

    with pytest.raises(PermissionDeniedError):
        auth_service.import_managed_accounts(
            schools["actor"],
            university_id=schools["b_id"],
            login_name="b-forbidden",
            role="station_manager",
            password="station2x",
            nickname="越权管理员",
        )
    with pytest.raises(PermissionDeniedError):
        auth_service.import_managed_accounts(
            schools["actor"],
            university_id=schools["a_id"],
            login_name="a-university-admin",
            role="university_admin",
            password="manager2x",
            nickname="越权校级管理员",
        )


def test_school_admin_roster_import_and_history_are_scoped(schools):
    csv_text = (
        "学号,姓名,手机号,校区代码,年级,班级,专业,学院\n"
        "2025901,甲新生,13800005901,A-MAIN,2025级,软工1班,软件工程,计算机学院\n"
    )
    batch = auth_service.import_students(
        schools["actor"],
        university_id=schools["a_id"],
        csv_bytes=csv_text.encode("utf-8"),
    )

    assert batch.university_id == schools["a_id"]
    assert batch.success_rows == 1
    assert [row.id for row in auth_service.list_import_batches(schools["actor"])] == [batch.id]

    with pytest.raises(PermissionDeniedError):
        auth_service.import_students(
            schools["actor"],
            university_id=schools["b_id"],
            csv_bytes=csv_text.replace("A-MAIN", "B-MAIN").encode("utf-8"),
        )


def test_school_admin_can_disable_student_and_end_manager_assignment(app, schools):
    student = auth_service.set_user_status(
        schools["actor"], schools["a_student_id"], status="disabled"
    )
    assert student.status == "disabled"

    manager = auth_service.set_user_status(
        schools["actor"], schools["a_manager_id"], status="disabled"
    )
    assert manager.status == "disabled"

    assignment = db.session.get(StationManagerAssignment, schools["a_assignment_id"])
    assert assignment.status == "ended"
    assert assignment.ended_on is not None
    assert db.session.query(AuditLog).filter_by(action="admin.user.status").count() == 2


def test_school_admin_status_permissions_are_limited(app, schools):
    actor = schools["actor"]

    with pytest.raises(PermissionDeniedError):
        auth_service.set_user_status(actor, actor.id, status="disabled")
    with pytest.raises(PermissionDeniedError):
        auth_service.set_user_status(actor, schools["b_student_id"], status="disabled")
    with pytest.raises(PermissionDeniedError):
        auth_service.set_user_status(actor, schools["b_admin_id"], status="disabled")
    with pytest.raises(PermissionDeniedError):
        auth_service.set_user_status(
            actor, schools["platform_admin_id"], status="disabled"
        )


def test_platform_admin_can_disable_scoped_user(schools):
    target = auth_service.set_user_status(
        schools["platform_actor"], schools["b_student_id"], status="disabled"
    )
    assert target.status == "disabled"


def test_platform_admin_can_disable_university_admin(schools):
    target = auth_service.set_user_status(
        schools["platform_actor"], schools["b_admin_id"], status="disabled"
    )
    assert target.status == "disabled"


def test_school_admin_users_and_roster_pages_are_scoped(client, schools):
    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": "university_admin"},
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page),
            "identifier": "school-a-admin",
            "password": "manager1",
        },
        follow_redirects=True,
    )

    users = client.get("/admin/users")
    assert users.status_code == 200
    users_html = users.get_data(as_text=True)
    assert "甲公益管理员" in users_html
    assert "乙公益管理员" not in users_html
    assert 'value="university_admin"' not in users_html

    imports = client.get("/admin/student-imports")
    assert imports.status_code == 200
    imports_html = imports.get_data(as_text=True)
    assert "甲大学" in imports_html
    assert "乙大学" not in imports_html

    status_form_page = client.get("/admin/users").get_data(as_text=True)
    response = client.post(
        f"/admin/users/{schools['a_student_id']}/status",
        data={"csrf_token": get_csrf_token(status_form_page), "status": "disabled"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "账号状态已更新" in response.get_data(as_text=True)
