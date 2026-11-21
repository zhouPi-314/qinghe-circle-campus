"""校级管理员角色快照与范围守卫的单元测试。"""

from __future__ import annotations

import pytest

from app.core.errors import PermissionDeniedError
from app.core.permissions import (
    CurrentUser,
    ensure_actor_university,
    is_university_manager,
)


def _actor(role: str = "university_admin", *, university_id: int | None = 1) -> CurrentUser:
    return CurrentUser(
        id=10,
        role=role,
        role_label=role,
        nickname="管理员",
        university_id=university_id,
        campus_id=None,
        login_name="manager",
        student_no=None,
    )


def test_university_admin_scope_accepts_same_school(monkeypatch):
    monkeypatch.setattr("app.core.permissions._university_status", lambda _id: "active")
    actor = _actor()

    assert ensure_actor_university(actor, actor.university_id) == actor.university_id


def test_university_admin_scope_rejects_other_school(monkeypatch):
    monkeypatch.setattr("app.core.permissions._university_status", lambda _id: "active")
    actor = _actor()

    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(actor, actor.university_id + 1)


def test_platform_admin_scope_is_global(monkeypatch):
    monkeypatch.setattr("app.core.permissions._university_status", lambda _id: "active")

    assert ensure_actor_university(_actor("platform_admin", university_id=None), 42) == 42


@pytest.mark.parametrize("role", ["student", "station_manager"])
def test_non_manager_scope_is_rejected(role):
    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(_actor(role), 1)


@pytest.mark.parametrize("status", ["inactive", None])
def test_inactive_or_missing_university_is_rejected(monkeypatch, status):
    monkeypatch.setattr("app.core.permissions._university_status", lambda _id: status)

    with pytest.raises(PermissionDeniedError):
        ensure_actor_university(_actor(), 1)


def test_university_manager_role_check():
    assert is_university_manager(_actor())
    assert is_university_manager(_actor("platform_admin", university_id=None))
    assert not is_university_manager(_actor("student"))
    assert not is_university_manager(None)
