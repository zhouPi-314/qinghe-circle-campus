"""校级管理员权限快照与数据库范围校验。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import db
from app.core.errors import PermissionDeniedError
from app.core.permissions import CurrentUser, ensure_actor_university, to_current_user
from app.models.university import University
from app.models.user import User
from app.services.auth_service import hash_password
from tests.fixtures.helpers import create_university, db_add

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
        admin = _create_university_admin(school_a, "school-a-admin")
        yield {
            "a_id": school_a.id,
            "b_id": school_b.id,
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
