"""注册验证请求的表结构、约束与模型映射。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.core.errors import ConflictError, InputError
from app.core.sms import MockSmsSender, SmsProviderError
from app.models.user import User
from app.models.verification import RegistrationVerificationRequest
from app.services import auth_service
from tests.fixtures.helpers import (
    create_campus,
    create_import_batch,
    create_platform_admin,
    create_registry_record,
    create_university,
)

pytestmark = pytest.mark.integration


def _request_row(*, university_id: int, registry_id: int | None, out_id: str, status="pending"):
    now = datetime.now(UTC)
    return RegistrationVerificationRequest(
        university_id=university_id,
        student_registry_record_id=registry_id,
        student_no_hash="a" * 64,
        phone_hash="b" * 64,
        code_hash="c" * 64 if status != "ignored" else None,
        salt="d" * 64 if status != "ignored" else None,
        provider="mock" if status != "ignored" else None,
        out_id=out_id,
        provider_message_id=None,
        status=status,
        request_ip_hash="e" * 64,
        failed_attempts=0,
        resend_after=now,
        expires_at=now + timedelta(minutes=5),
        sent_at=None,
        consumed_at=None,
        created_at=now,
    )


def test_registration_verification_table_and_columns(app):
    with app.app_context():
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns(
            "registration_verification_requests"
        )}

    assert columns == {
        "id",
        "university_id",
        "student_registry_record_id",
        "student_no_hash",
        "phone_hash",
        "code_hash",
        "salt",
        "provider",
        "out_id",
        "provider_message_id",
        "status",
        "request_ip_hash",
        "failed_attempts",
        "resend_after",
        "expires_at",
        "sent_at",
        "consumed_at",
        "created_at",
    }


def test_registry_has_composite_university_key(app):
    with app.app_context():
        constraints = {
            tuple(item["column_names"])
            for item in inspect(db.engine).get_unique_constraints("student_registry_records")
        }

    assert ("id", "university_id") in constraints


def test_ignored_request_allows_null_registry_and_code(app):
    with app.app_context():
        university = create_university()
        db.session.add(
            _request_row(
                university_id=university.id,
                registry_id=None,
                out_id="ignored-1",
                status="ignored",
            )
        )
        db.session.commit()

        assert db.session.query(RegistrationVerificationRequest).count() == 1


@pytest.mark.parametrize("hash_name", ["student_no_hash", "phone_hash", "request_ip_hash"])
def test_hashes_must_be_sha256_hex(app, hash_name):
    with app.app_context():
        university = create_university()
        row = _request_row(
            university_id=university.id,
            registry_id=None,
            out_id=f"bad-hash-{hash_name}",
            status="ignored",
        )
        setattr(row, hash_name, "not-a-hash")
        db.session.add(row)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_only_one_active_challenge_per_registry_record(app):
    with app.app_context():
        university = create_university()
        campus = create_campus(university)
        admin, _ = create_platform_admin()
        batch = create_import_batch(university, admin)
        registry = create_registry_record(university, campus, batch)

        db.session.add(
            _request_row(
                university_id=university.id,
                registry_id=registry.id,
                out_id="active-1",
                status="pending",
            )
        )
        db.session.commit()
        db.session.add(
            _request_row(
                university_id=university.id,
                registry_id=registry.id,
                out_id="active-2",
                status="sent",
            )
        )

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_active_challenge_requires_registry_and_local_mock_fields(app):
    with app.app_context():
        university = create_university()
        row = _request_row(
            university_id=university.id,
            registry_id=None,
            out_id="invalid-active",
            status="pending",
        )
        db.session.add(row)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_out_id_is_unique(app):
    with app.app_context():
        university = create_university()
        db.session.add(
            _request_row(
                university_id=university.id,
                registry_id=None,
                out_id="duplicate",
                status="ignored",
            )
        )
        db.session.commit()
        db.session.add(
            _request_row(
                university_id=university.id,
                registry_id=None,
                out_id="duplicate",
                status="ignored",
            )
        )

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_schema_defines_expected_indexes(app):
    with app.app_context():
        rows = db.session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'registration_verification_requests'"
            )
        ).scalars()
        indexes = set(rows)

    assert "uq_active_registration_verification" in indexes
    assert "ix_registration_verification_phone_created" in indexes
    assert "ix_registration_verification_ip_created" in indexes


@pytest.fixture
def registration_world(app):
    with app.app_context():
        university = create_university(code="510901", name="注册测试大学")
        campus = create_campus(university, code="REG", name="注册校区")
        admin, _ = create_platform_admin(login_name="reg-admin")
        batch = create_import_batch(university, admin)
        record = create_registry_record(
            university,
            campus,
            batch,
            student_no="2026901",
            full_name="注册测试生",
            phone="13800006901",
        )
        yield {
            "university_id": university.id,
            "campus_id": campus.id,
            "record_id": record.id,
        }


def _allow_captcha(monkeypatch, answer="A7B9"):
    monkeypatch.setattr(
        auth_service,
        "verify_captcha",
        lambda _session, submitted: submitted == answer,
    )
    return answer


def _request_code(app, world, *, captcha_answer="A7B9", student_no="2026901", phone="13800006901"):
    with app.test_request_context():
        result = auth_service.request_registration_code(
            university_id=world["university_id"],
            campus_id=world["campus_id"],
            student_no=student_no,
            phone=phone,
            captcha_answer=captcha_answer,
            request_ip="203.0.113.9",
        )
        return dict(result)


def _register(app, world, request_id, code):
    return auth_service.register_student(
        university_id=world["university_id"],
        campus_id=world["campus_id"],
        student_no="2026901",
        phone="13800006901",
        password="student1a",
        verification_request_id=request_id,
        sms_code=code,
    )


def test_captcha_is_checked_before_roster_lookup(app, monkeypatch, registration_world):
    _allow_captcha(monkeypatch)

    with pytest.raises(InputError) as raised:
        _request_code(app, registration_world, captcha_answer="WRONG")

    assert "captcha" in raised.value.field_errors
    with app.app_context():
        assert db.session.query(RegistrationVerificationRequest).count() == 0


def test_mismatch_returns_generic_message_and_records_ignored(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)

    result = _request_code(
        app,
        registration_world,
        captcha_answer=answer,
        student_no="9999999",
    )

    assert result["message"] == auth_service.REGISTRATION_CODE_GENERIC_MESSAGE
    with app.app_context():
        row = db.session.query(RegistrationVerificationRequest).one()
        assert row.status == "ignored"
        assert row.student_registry_record_id is None
        assert row.provider is None


def test_matched_and_mismatched_responses_are_indistinguishable(
    app, monkeypatch, registration_world
):
    answer = _allow_captcha(monkeypatch)

    mismatched = _request_code(
        app,
        registration_world,
        captcha_answer=answer,
        student_no="9999999",
    )
    matched = _request_code(app, registration_world, captcha_answer=answer)

    assert matched == mismatched


def test_request_sends_once_and_enforces_60_second_cooldown(
    app, monkeypatch, registration_world
):
    answer = _allow_captcha(monkeypatch)

    class CountingSender(MockSmsSender):
        def __init__(self):
            super().__init__()
            self.sent = 0

        def send_register_code(self, phone, out_id):
            self.sent += 1
            return super().send_register_code(phone, out_id)

    sender = CountingSender()
    original = app.extensions["sms_sender"]
    app.extensions["sms_sender"] = sender
    try:
        first = _request_code(app, registration_world, captcha_answer=answer)
        second = _request_code(app, registration_world, captcha_answer=answer)
    finally:
        app.extensions["sms_sender"] = original

    assert first["message"] == second["message"]
    assert sender.sent == 1
    with app.app_context():
        assert db.session.query(RegistrationVerificationRequest).count() == 1


def test_request_can_resend_after_cooldown(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)

    class CountingSender(MockSmsSender):
        def __init__(self):
            super().__init__()
            self.sent = 0

        def send_register_code(self, phone, out_id):
            self.sent += 1
            return super().send_register_code(phone, out_id)

    sender = CountingSender()
    original = app.extensions["sms_sender"]
    app.extensions["sms_sender"] = sender
    try:
        _request_code(app, registration_world, captcha_answer=answer)
        with app.app_context():
            active = db.session.query(RegistrationVerificationRequest).one()
            active.resend_after = active.created_at
            db.session.commit()
        _request_code(app, registration_world, captcha_answer=answer)
    finally:
        app.extensions["sms_sender"] = original

    assert sender.sent == 2
    with app.app_context():
        statuses = [
            row.status
            for row in db.session.query(RegistrationVerificationRequest).order_by(
                RegistrationVerificationRequest.id
            )
        ]
    assert statuses == ["expired", "sent"]


def test_provider_failure_marks_failed_and_creates_no_user(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)

    class FailingSender(MockSmsSender):
        def send_register_code(self, phone, out_id):
            raise SmsProviderError("短信服务暂时不可用，请稍后重试。")

    original = app.extensions["sms_sender"]
    app.extensions["sms_sender"] = FailingSender()
    try:
        with pytest.raises(SmsProviderError):
            _request_code(app, registration_world, captcha_answer=answer)
    finally:
        app.extensions["sms_sender"] = original

    with app.app_context():
        row = db.session.query(RegistrationVerificationRequest).one()
        assert row.status == "failed"
        assert db.session.query(User).filter_by(student_no="2026901").count() == 0


def test_mock_verified_registration_consumes_challenge(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)
    _request_code(app, registration_world, captcha_answer=answer)

    with app.app_context():
        challenge = db.session.query(RegistrationVerificationRequest).one()
        challenge_id = challenge.id
        user = _register(app, registration_world, challenge_id, "123456")
        assert user.student_no == "2026901"
        db.session.refresh(challenge)
        assert challenge.status == "consumed"

        with pytest.raises((ConflictError, InputError)):
            _register(app, registration_world, challenge_id, "123456")


def test_expired_challenge_is_rejected(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)
    _request_code(app, registration_world, captcha_answer=answer)

    with app.app_context():
        challenge = db.session.query(RegistrationVerificationRequest).one()
        challenge.created_at = datetime.now(UTC) - timedelta(seconds=301)
        challenge.resend_after = challenge.created_at
        challenge.expires_at = challenge.created_at + timedelta(seconds=1)
        challenge_id = challenge.id
        db.session.commit()

        with pytest.raises(InputError):
            _register(app, registration_world, challenge_id, "123456")
        db.session.refresh(challenge)
        assert challenge.status == "expired"


def test_five_wrong_codes_fail_challenge(app, monkeypatch, registration_world):
    answer = _allow_captcha(monkeypatch)
    _request_code(app, registration_world, captcha_answer=answer)

    with app.app_context():
        challenge_id = db.session.query(RegistrationVerificationRequest).one().id
        for _ in range(5):
            with pytest.raises(InputError):
                _register(app, registration_world, challenge_id, "000000")
        challenge = db.session.get(RegistrationVerificationRequest, challenge_id)
        assert challenge.failed_attempts == 5
        assert challenge.status == "failed"

        with pytest.raises(InputError):
            _register(app, registration_world, challenge_id, "123456")


def test_production_requires_verified_registration(app, monkeypatch, registration_world):
    monkeypatch.setitem(app.config, "TESTING", False)

    with app.app_context():
        with pytest.raises(InputError):
            auth_service.register_student(
                university_id=registration_world["university_id"],
                campus_id=registration_world["campus_id"],
                student_no="2026901",
                phone="13800006901",
                password="student1a",
            )
