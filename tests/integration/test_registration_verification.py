"""注册验证请求的表结构、约束与模型映射。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.verification import RegistrationVerificationRequest
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
