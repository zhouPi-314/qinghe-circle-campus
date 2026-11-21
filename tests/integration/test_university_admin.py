"""校级管理员权限快照与数据库范围校验。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import db
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.permissions import CurrentUser, ensure_actor_university, to_current_user
from app.models.circulation import CirculationRequest
from app.models.governance import AuditLog, Dispute
from app.models.university import Station, StationManagerAssignment, University
from app.models.user import User
from app.services import (
    auth_service,
    handover_service,
    item_service,
    notification_service,
    org_service,
)
from app.services.auth_service import hash_password
from tests.fixtures.helpers import (
    assign_manager,
    create_campus,
    create_category,
    create_item,
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


def _login_admin(client, role: str, identifier: str, password: str) -> None:
    page = client.get("/auth/identity").get_data(as_text=True)
    client.post(
        "/auth/identity",
        data={"csrf_token": get_csrf_token(page), "role": role},
        follow_redirects=True,
    )
    page = client.get("/auth/login").get_data(as_text=True)
    client.post(
        "/auth/login",
        data={
            "csrf_token": get_csrf_token(page),
            "identifier": identifier,
            "password": password,
        },
        follow_redirects=True,
    )


def test_school_admin_creates_station_from_http_form(client, schools):
    _login_admin(client, "university_admin", "school-a-admin", "manager1")
    page = client.get("/admin/organizations").get_data(as_text=True)
    response = client.post(
        "/admin/organizations/stations",
        data={
            "csrf_token": get_csrf_token(page),
            "campus_id": str(schools["a_campus_id"]),
            "name": "HTTP 校级站点",
            "station_type": "mixed",
            "address": "甲校东门",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    station = db.session.scalar(select(Station).where(Station.name == "HTTP 校级站点"))
    assert station is not None
    assert station.university_id == schools["a_id"]


def test_platform_admin_creates_station_from_http_form(client, schools):
    _login_admin(client, "platform_admin", "platform-a", "admin12345")
    page = client.get("/admin/organizations").get_data(as_text=True)
    response = client.post(
        "/admin/organizations/stations",
        data={
            "csrf_token": get_csrf_token(page),
            "campus_id": str(schools["b_campus_id"]),
            "name": "HTTP 平台站点",
            "station_type": "charity",
            "address": "乙校南门",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    station = db.session.scalar(select(Station).where(Station.name == "HTTP 平台站点"))
    assert station is not None
    assert station.university_id == schools["b_id"]


def test_school_admin_cannot_create_station_from_other_school_http(client, schools):
    _login_admin(client, "university_admin", "school-a-admin", "manager1")
    page = client.get("/admin/organizations").get_data(as_text=True)
    response = client.post(
        "/admin/organizations/stations",
        data={
            "csrf_token": get_csrf_token(page),
            "campus_id": str(schools["b_campus_id"]),
            "name": "跨校 HTTP 站点",
            "station_type": "mixed",
            "address": "乙校北门",
        },
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert db.session.scalar(select(Station).where(Station.name == "跨校 HTTP 站点")) is None


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


@pytest.fixture
def governance_world(app, schools):
    with app.app_context():
        school_a = db.session.get(University, schools["a_id"])
        school_b = db.session.get(University, schools["b_id"])
        campus_a = db.session.get(University, schools["a_id"]).campuses[0]
        campus_b = db.session.get(University, schools["b_id"]).campuses[0]
        owner_a = db.session.get(User, schools["a_student_id"])
        owner_b = db.session.get(User, schools["b_student_id"])
        borrower_a = create_student_user(
            school_a, campus_a, student_no="2025021", phone="13900005021"
        )
        borrower_b = create_student_user(
            school_b, campus_b, student_no="2025022", phone="13900005022"
        )
        category = create_category()
        item_a = create_item(owner_a, category.id, campus_a.id, title="甲审核物品")
        item_b = create_item(owner_b, category.id, campus_b.id, title="乙审核物品")
        dispute_item_a = create_item(
            owner_a, category.id, campus_a.id, title="甲争议物品"
        )
        dispute_item_b = create_item(
            owner_b, category.id, campus_b.id, title="乙争议物品"
        )
        now = datetime.now(UTC)
        dispute_item_a.status = "on_hold"
        dispute_item_b.status = "on_hold"
        request_a = CirculationRequest(
            university_id=schools["a_id"],
            item_id=dispute_item_a.id,
            requester_user_id=borrower_a.id,
            owner_user_id=owner_a.id,
            mode="borrow",
            status="disputed",
            created_at=now,
            updated_at=now,
        )
        request_b = CirculationRequest(
            university_id=schools["b_id"],
            item_id=dispute_item_b.id,
            requester_user_id=borrower_b.id,
            owner_user_id=owner_b.id,
            mode="borrow",
            status="disputed",
            created_at=now,
            updated_at=now,
        )
        db.session.add_all([request_a, request_b])
        db.session.flush()
        dispute_a = Dispute(
            university_id=schools["a_id"],
            circulation_request_id=request_a.id,
            opened_by_user_id=borrower_a.id,
            reason="甲争议",
            status="open",
            created_at=now,
            updated_at=now,
        )
        dispute_b = Dispute(
            university_id=schools["b_id"],
            circulation_request_id=request_b.id,
            opened_by_user_id=borrower_b.id,
            reason="乙争议",
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.session.add_all([dispute_a, dispute_b])
        notification_service.record_audit(
            actor_user_id=schools["actor"].id,
            university_id=schools["a_id"],
            action="test.audit.a",
            entity_type="test",
        )
        notification_service.record_audit(
            actor_user_id=schools["b_admin_id"],
            university_id=schools["b_id"],
            action="test.audit.b",
            entity_type="test",
        )
        db.session.commit()
        yield {
            "item_a_id": item_a.id,
            "item_b_id": item_b.id,
            "dispute_a_id": dispute_a.id,
            "dispute_b_id": dispute_b.id,
        }


def test_school_admin_moderation_lists_are_scoped(governance_world, schools):
    item_ids = {item.id for item in item_service.list_recent_items(schools["actor"])}
    assert governance_world["item_a_id"] in item_ids
    assert governance_world["item_b_id"] not in item_ids

    platform_ids = {
        item.id for item in item_service.list_recent_items(schools["platform_actor"])
    }
    assert {governance_world["item_a_id"], governance_world["item_b_id"]} <= platform_ids


def test_school_admin_can_force_off_own_item_only(governance_world, schools):
    item = item_service.change_item_shelf_state(
        schools["actor"],
        governance_world["item_a_id"],
        action="force_off_shelf",
        reason="本校违规",
    )
    assert item.moderation_status == "hidden"

    with pytest.raises(NotFoundError):
        item_service.change_item_shelf_state(
            schools["actor"],
            governance_world["item_b_id"],
            action="force_off_shelf",
            reason="跨校违规",
        )


def test_school_admin_disputes_are_scoped(governance_world, schools):
    own_ids = {dispute.id for dispute in handover_service.list_open_disputes(schools["actor"])}
    assert own_ids == {governance_world["dispute_a_id"]}

    platform_ids = {
        dispute.id
        for dispute in handover_service.list_open_disputes(schools["platform_actor"])
    }
    assert platform_ids == {
        governance_world["dispute_a_id"],
        governance_world["dispute_b_id"],
    }


def test_school_admin_can_resolve_own_dispute_only(governance_world, schools):
    dispute = handover_service.resolve_dispute(
        schools["actor"],
        governance_world["dispute_a_id"],
        resolution="本校处理完成",
    )
    assert dispute.status == "resolved"

    with pytest.raises(NotFoundError):
        handover_service.resolve_dispute(
            schools["actor"],
            governance_world["dispute_b_id"],
            resolution="跨校处理",
        )


def test_school_admin_audit_logs_are_scoped(governance_world, schools):
    own_actions = {
        log.action for log in notification_service.list_audit_logs(schools["actor"])
    }
    assert "test.audit.a" in own_actions
    assert "test.audit.b" not in own_actions

    platform_actions = {
        log.action
        for log in notification_service.list_audit_logs(schools["platform_actor"])
    }
    assert {"test.audit.a", "test.audit.b"} <= platform_actions


def test_school_admin_governance_pages_are_scoped(client, governance_world, schools):
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

    moderation = client.get("/admin/moderation")
    assert moderation.status_code == 200
    html = moderation.get_data(as_text=True)
    assert "甲审核物品" in html
    assert "乙审核物品" not in html

    disputes = client.get("/admin/disputes")
    assert disputes.status_code == 200
    html = disputes.get_data(as_text=True)
    assert "甲争议" in html
    assert "乙争议" not in html

    audit = client.get("/admin/audit")
    assert audit.status_code == 200
    html = audit.get_data(as_text=True)
    assert "test.audit.a" in html
    assert "test.audit.b" not in html
