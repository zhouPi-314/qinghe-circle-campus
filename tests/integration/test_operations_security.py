"""Platform operations and registration abuse controls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest
from sqlalchemy import select

from app import db
from app.core.errors import PermissionDeniedError, TooManyRequestsError
from app.core.permissions import to_current_user
from app.models.security import ApplicationEvent, SecurityBlock, SecurityEvent
from app.models.user import User
from app.models.verification import RegistrationVerificationRequest
from app.services import auth_service, operations_service
from tests.fixtures.helpers import (
    create_campus,
    create_import_batch,
    create_platform_admin,
    create_registry_record,
    create_university,
)
from tests.integration.test_register_and_login import get_csrf_token

pytestmark = pytest.mark.integration


@pytest.fixture
def security_world(app):
    with app.app_context():
        university = create_university(code="510990", name="安全测试大学")
        campus = create_campus(university, code="SEC", name="安全校区")
        platform, _ = create_platform_admin(login_name="sec-admin", password="admin12345")
        batch = create_import_batch(university, platform)
        create_registry_record(
            university,
            campus,
            batch,
            student_no="2026999",
            full_name="安全测试生",
            phone="13800006999",
        )
        yield {
            "university_id": university.id,
            "campus_id": campus.id,
            "platform_id": platform.id,
        }


def _request_mismatch(app, monkeypatch, world, ip="203.0.113.77"):
    monkeypatch.setattr(
        auth_service,
        "verify_captcha",
        lambda _session, answer: answer == "TEST",
    )
    with app.test_request_context():
        return auth_service.request_registration_code(
            university_id=world["university_id"],
            campus_id=world["campus_id"],
            student_no="9999999",
            phone="13800006999",
            captcha_answer="TEST",
            request_ip=ip,
        )


def test_ninth_registration_request_from_ip_creates_block_and_attack_event(
    app, monkeypatch, security_world
):
    for _ in range(8):
        result = _request_mismatch(app, monkeypatch, security_world)
        assert result["message"] == auth_service.REGISTRATION_CODE_GENERIC_MESSAGE

    with pytest.raises(TooManyRequestsError):
        _request_mismatch(app, monkeypatch, security_world)

    with app.app_context():
        block = db.session.scalar(select(SecurityBlock).where(SecurityBlock.status == "active"))
        event = db.session.scalar(
            select(SecurityEvent).where(SecurityEvent.category == "sms_ip_threshold")
        )
        assert block is not None
        assert block.ends_at > datetime.now(UTC)
        assert event is not None
        assert event.severity == "high"


def test_active_block_unique_and_advisory_lock_serializes_same_ip(
    app, monkeypatch, security_world
):
    subject_hash = auth_service._registration_hash("request-ip", "203.0.113.88")
    for _ in range(8):
        _request_mismatch(app, monkeypatch, security_world, ip="203.0.113.88")

    barrier = Barrier(2)
    outcomes = []

    def attempt():
        with app.app_context():
            barrier.wait()
            try:
                operations_service.ensure_ip_allowed(
                    subject_hash,
                    university_id=security_world["university_id"],
                    route="/auth/register/sms-code",
                )
            except TooManyRequestsError:
                outcomes.append("blocked")
            else:
                outcomes.append("allowed")

    threads = [Thread(target=attempt), Thread(target=attempt)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes == ["blocked", "blocked"]
    with app.app_context():
        active = db.session.scalars(
            select(SecurityBlock).where(
                SecurityBlock.subject_hash == subject_hash,
                SecurityBlock.status == "active",
            )
        ).all()
        assert len(active) == 1


def test_expired_block_no_longer_blocks_registration(app, monkeypatch, security_world):
    for _ in range(8):
        _request_mismatch(app, monkeypatch, security_world)
    with pytest.raises(TooManyRequestsError):
        _request_mismatch(app, monkeypatch, security_world)

    with app.app_context():
        block = db.session.scalar(select(SecurityBlock).where(SecurityBlock.status == "active"))
        block.ends_at = datetime.now(UTC) - timedelta(seconds=1)
        block.starts_at = block.ends_at - timedelta(minutes=15)
        for request in db.session.scalars(select(RegistrationVerificationRequest)).all():
            request.created_at = datetime.now(UTC) - timedelta(minutes=11)
        db.session.commit()

    result = _request_mismatch(app, monkeypatch, security_world)
    assert result["message"] == auth_service.REGISTRATION_CODE_GENERIC_MESSAGE
    with app.app_context():
        expired = db.session.scalar(
            select(SecurityBlock).order_by(SecurityBlock.id.desc())
        )
        assert expired.status == "expired"


def test_platform_admin_can_review_and_revoke_block(app, security_world):
    with app.app_context():
        platform = db.session.get(User, security_world["platform_id"])
        actor = to_current_user(platform)
        block = operations_service.create_ip_block(
            subject_hash="a" * 64,
            category="sms_ip_threshold",
            duration=timedelta(minutes=15),
            detail={"attempts": 8},
        )
        snapshot = operations_service.operations_snapshot(actor)
        assert snapshot["active_blocks"] == 1

        revoked = operations_service.set_block_disposition(
            actor,
            block.id,
            action="revoke",
            reason="确认误报",
        )
        assert revoked.status == "revoked"
        assert operations_service.operations_snapshot(actor)["active_blocks"] == 0


def test_school_admin_cannot_access_operations(app, security_world):
    with app.app_context():
        from app.models.user import User

        university_id = security_world["university_id"]
        admin = User(
            university_id=university_id,
            login_name="school-sec",
            password_hash="unused",
            nickname="校级管理员",
            role="university_admin",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.session.add(admin)
        db.session.commit()
        actor = to_current_user(admin)

    with pytest.raises(PermissionDeniedError):
        operations_service.operations_snapshot(actor)


def test_application_event_summary_is_stored_without_sensitive_fields(app):
    with app.app_context():
        operations_service.record_application_event(
            level="error",
            event_code="unexpected_error",
            request_id="req-123",
            route="/auth/register",
            method="POST",
            status_code=500,
            summary="系统遇到意外错误",
            detail={"type": "RuntimeError", "phone": "must-not-store"},
        )
        event = db.session.scalar(select(ApplicationEvent))
        assert event.request_id == "req-123"
        assert "must-not-store" not in str(event.detail)


def test_operations_page_renders_for_platform_admin(client, security_world):
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
            "identifier": "sec-admin",
            "password": "admin12345",
        },
        follow_redirects=True,
    )

    response = client.get("/admin/operations")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "运维与安全" in html
    assert "恶意攻击分类" in html
    assert "应用报错与日志" in html
