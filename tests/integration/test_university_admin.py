"""校级管理员权限快照与数据库范围校验。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import db
from app.core.errors import PermissionDeniedError
from app.core.permissions import CurrentUser, ensure_actor_university, to_current_user
from app.models.university import University
from app.models.user import User
from app.services import org_service
from app.services.auth_service import hash_password
from tests.fixtures.helpers import (
    create_campus,
    create_station,
    create_station_manager_user,
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
        manager_a = create_station_manager_user(
            school_a, login_name="a-station", nickname="甲公益管理员"
        )
        manager_b = create_station_manager_user(
            school_b, login_name="b-station", nickname="乙公益管理员"
        )
        station_a = create_station(school_a, campus_a, name="甲站点")
        station_b = create_station(school_b, campus_b, name="乙站点")
        yield {
            "a_id": school_a.id,
            "b_id": school_b.id,
            "a_campus_id": campus_a.id,
            "b_campus_id": campus_b.id,
            "a_manager_id": manager_a.id,
            "b_manager_id": manager_b.id,
            "a_station_id": station_a.id,
            "b_station_id": station_b.id,
            "actor": to_current_user(admin),
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
